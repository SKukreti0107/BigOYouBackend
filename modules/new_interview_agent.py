import uuid
from typing import Literal
from pydantic import BaseModel
from modules.db import (
    engine,
    InterviewPhase,
    Interview_Session,
    Problems,
    Problem_Reference,
    Session_Code_State,
    Session_Message,
    Session_Feedback,
    Session_Metrics,
)
from fastapi import APIRouter, Depends, HTTPException, status
from helpers.get_session_data import parse_session_and_user_ids, get_session_row,get_session_timer
from helpers.auth_deps import get_current_user
from helpers.populate_sesson_metrics import populate_total_time_spent_sec
from sqlmodel import Session, select
from services.ai_agent.schemas import InterviewAgentState
from datetime import timedelta
from langchain_core.messages import HumanMessage
from services.ai_agent.langgraph_agent import graph
from services.ai_agent.helpers.agent_runners import run_interview_turn,get_last_ai_message
router = APIRouter()


@router.get("/interview/agent_messages")
def agent_messages(session_id: str, user_id: str = Depends(get_current_user)):
    """Read chat messages directly from the LangGraph persistent checkpoint."""
    config = {"configurable": {"thread_id": session_id}}
    try:
        snapshot = graph.get_state(config)
        if not snapshot or not hasattr(snapshot, "values"):
            return []

        messages = snapshot.values.get("messages", [])
        result = []
        for msg in messages:
            role = "ai" if msg.type == "ai" else "user"
            # Skip system-injected context messages (internal assessment state)
            content = str(msg.content or "")
            if content.startswith("**Internal Assessment State:**"):
                continue
            result.append({"role": role, "content": content})
        return result
    except Exception as e:
        print(f"Error reading agent messages: {e}")
        return []


#-------------------------------------------------------------------
#Schemas and helpers 
class PhaseRequest(BaseModel):
    session_id: str
    message: str
    code: str | None = None
    language: str | None = None
    role: Literal["user", "system"] = "user"
    time_expired: bool | None = None
    extra_time_used: bool | None = None
    extension_count: int | None = None
    session_ended_by: str | None = None


class AgentInitRequest(BaseModel):
    session_id: str
    message: str | None = "[SYSTEM EVENT] Start the interview"
    role: Literal["user", "system"] = "system"


class TimeoutActionRequest(BaseModel):
    session_id: str
    action: Literal["REVIEW", "END_FEEDBACK", "EXTEND"]
    extension_minutes: int = 15


def _get_session_or_404(db: Session, session_id: str, user_id: str) -> Interview_Session:
    session_uuid, user_uuid = parse_session_and_user_ids(session_id, user_id)
    return get_session_row(db, session_uuid, user_uuid)


def _load_problem_context(db: Session, session_row: Interview_Session) -> tuple[str, dict]:
    problem = db.exec(
        select(Problems).where(Problems.problem_id == session_row.problem_id)
    ).first()
    if not problem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Problem not found",
        )

    reference = db.exec(
        select(Problem_Reference).where(
            Problem_Reference.problem_id == session_row.problem_id
        )
    ).first()

    references = {
        "title": problem.title,
        "optimal_approach": reference.optimal_approach,
        "time_complexity": reference.time_complexity,
        "space_complexity": reference.space_complexity,
        "key_insights": reference.key_insights,
        "common_pitfalls": reference.common_pitfalls,
        "pseudocode": reference.pseudocode,
    } if reference else {}

    return problem.statement, references

def _get_latest_code(db: Session, session_id: uuid.UUID) -> str:
    latest = db.exec(
        select(Session_Code_State)
        .where(Session_Code_State.session_id == session_id)
        .order_by(Session_Code_State.created_at.desc())
        .limit(1)
    ).first()
    return latest.code if latest else ""


def _persist_turn_data(
    payload: PhaseRequest | AgentInitRequest, 
    user_id: str, 
    res: dict
):
    with Session(engine) as db:
        session_row = _get_session_or_404(db, payload.session_id, user_id)
        
        # 1. Handle Code Snapshot
        code = getattr(payload, "code", None)
        if code is not None:
            db.add(
                Session_Code_State(
                    session_id=session_row.session_id,
                    code=code,
                    language=getattr(payload, "language", ""),
                )
            )

        # 2. Sync Session Phase & Status
        new_phase = res.get("phase")
        if new_phase:
            if new_phase == InterviewPhase.FEEDBACK and session_row.phase != InterviewPhase.FEEDBACK:
                session_row.status = "CLOSED"
                populate_total_time_spent_sec(session_row.session_id, user_id)
            session_row.phase = new_phase

            # 3. Handle Structured Feedback
            if new_phase == InterviewPhase.FEEDBACK:
                fb = res.get("feedback")
                if fb:
                    fb_dict = fb.model_dump() if hasattr(fb, "model_dump") else fb
                    existing_fb = db.exec(
                        select(Session_Feedback)
                        .where(Session_Feedback.session_id == session_row.session_id)
                    ).first()
                    if existing_fb:
                        existing_fb.feedback_json = fb_dict
                        db.add(existing_fb)
                    else:
                        db.add(
                            Session_Feedback(
                                session_id=session_row.session_id,
                                feedback_json=fb_dict,
                            )
                        )

        db.add(session_row)
        db.commit()


def _sync_runtime_state_before_turn(payload: PhaseRequest):
    state_updates = {}

    if payload.code:
        state_updates["user_code"] = payload.code

    if payload.time_expired is not None:
        state_updates["time_expired"] = payload.time_expired

    if payload.extra_time_used is not None:
        state_updates["extra_time_used"] = payload.extra_time_used

    if payload.extension_count is not None:
        state_updates["extension_count"] = payload.extension_count

    if payload.session_ended_by is not None:
        state_updates["session_ended_by"] = payload.session_ended_by

    if state_updates:
        config = {"configurable": {"thread_id": payload.session_id}}
        graph.update_state(config, state_updates)


@router.post("/interview/timeout_action")
def timeout_action(payload: TimeoutActionRequest, user_id: str = Depends(get_current_user)):
    with Session(engine) as db:
        session_row = _get_session_or_404(db, payload.session_id, user_id)

    config = {"configurable": {"thread_id": payload.session_id}}
    snapshot = graph.get_state(config)
    values = snapshot.values if snapshot and hasattr(snapshot, "values") else {}

    extension_count = int(values.get("extension_count") or 0)
    max_extensions = 1

    if payload.action == "EXTEND":
        if extension_count >= max_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Extension limit reached",
            )

        next_count = extension_count + 1
        graph.update_state(
            config,
            {
                "time_expired": True,
                "extra_time_used": True,
                "extension_count": next_count,
                "session_ended_by": "TIMEOUT_EXTEND",
            },
        )

        return {
            "action": "EXTEND",
            "allowed": True,
            "extension_seconds": payload.extension_minutes * 60,
            "extension_count": next_count,
            "max_extensions": max_extensions,
        }

    graph.update_state(
        config,
        {
            "time_expired": True,
            "extra_time_used": bool(values.get("extra_time_used") or False),
            "extension_count": extension_count,
            "session_ended_by": "TIMEOUT_END",
        },
    )

    return {
        "action": payload.action,
        "allowed": True,
        "extension_count": extension_count,
        "max_extensions": max_extensions,
    }


#-------------------------------------------------------------------
#routers
@router.post("/interview/agent_init")
def agent_init(payload: AgentInitRequest, user_id: str = Depends(get_current_user)):
    with Session(engine) as db:
        session_row = _get_session_or_404(db, payload.session_id, user_id)
        problem_statement, problem_references = _load_problem_context(db, session_row)
        
    # build graph state
    state: InterviewAgentState = {
        "session_id": str(payload.session_id),
        "messages": [HumanMessage(content=payload.message)],
        "phase": InterviewPhase.PROBLEM_DISCUSSION.value,
        "problem_statement": problem_statement,
        "problem_references": problem_references,
        "execution_attempts": 0,
        "discussion_turns": 0,
        "review_turns": 0,
        "coding_turns": 0,
    }

    res = run_interview_turn(graph=graph, state=state, thread_id=payload.session_id, user_input=payload.message, is_first=True)
    _persist_turn_data(payload, user_id, res)
    return res
    

@router.post("/interview/problem_discussion")
def problem_discussion(payload: PhaseRequest, user_id: str = Depends(get_current_user)):
    _sync_runtime_state_before_turn(payload)
    res = run_interview_turn(graph=graph, thread_id=payload.session_id, user_input=payload.message)
    _persist_turn_data(payload, user_id, res)
    return res


@router.post("/interview/coding")
def coding(payload: PhaseRequest, user_id: str = Depends(get_current_user)):
    _sync_runtime_state_before_turn(payload)
    res = run_interview_turn(graph=graph, thread_id=payload.session_id, user_input=payload.message)
    _persist_turn_data(payload, user_id, res)
    return res


@router.post("/interview/review")
def review(payload: PhaseRequest, user_id: str = Depends(get_current_user)):
    _sync_runtime_state_before_turn(payload)
    res = run_interview_turn(graph=graph, thread_id=payload.session_id, user_input=payload.message)
    _persist_turn_data(payload, user_id, res)
    return res


@router.post("/interview/feedback")
def feedback(payload: PhaseRequest, user_id: str = Depends(get_current_user)):
    # Inject metrics into LangGraph checkpointer before invoking the feedback phase
    with Session(engine) as db:
        session_row = _get_session_or_404(db, payload.session_id, user_id)
        
        # Stop timer to get the final total_time_spent_sec populated
        populate_total_time_spent_sec(session_row.session_id, user_id)

        metrics = db.exec(
            select(Session_Metrics).where(Session_Metrics.session_id == session_row.session_id)
        ).first()

        state_updates = {}
        if metrics:
            state_updates["total_time_spent_sec"] = metrics.total_time_spent_sec or 0
            state_updates["total_submissions"] = metrics.total_submissions or 0
            state_updates["hints_used"] = metrics.hints_used or 0

        latest_code = _get_latest_code(db, session_row.session_id)
        if latest_code:
            state_updates["user_code"] = latest_code

        if payload.time_expired is not None:
            state_updates["time_expired"] = payload.time_expired

        if payload.extra_time_used is not None:
            state_updates["extra_time_used"] = payload.extra_time_used

        if payload.extension_count is not None:
            state_updates["extension_count"] = payload.extension_count

        if payload.session_ended_by is not None:
            state_updates["session_ended_by"] = payload.session_ended_by

        if state_updates:
            config = {"configurable": {"thread_id": payload.session_id}}
            graph.update_state(config, state_updates)

    res = run_interview_turn(graph=graph, thread_id=payload.session_id, user_input=payload.message)
    _persist_turn_data(payload, user_id, res)
    return res


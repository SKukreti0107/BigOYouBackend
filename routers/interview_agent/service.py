import uuid

from fastapi import HTTPException, status
from langchain_core.messages import HumanMessage
from sqlmodel import Session, select

from helpers.session.get_session_data import parse_session_and_user_ids, get_session_row
from helpers.session.update_sesson_metrics import populate_total_time_spent_sec
from modules.db import (
    engine,
    InterviewPhase,
    Interview_Session,
    Problems,
    Problem_Reference,
    Session_Code_State,
    Session_Feedback,
    Session_Metrics,
)
from modules.schemas import PhaseRequest, AgentInitRequest, TimeoutActionRequest
from services.ai_agent.helpers.message_normalizer import (
    normalize_message_role,
    normalize_message_text,
)
from services.ai_agent.schemas import InterviewAgentState


def get_agent_messages(graph, session_id: str) -> list[dict]:
    config = {"configurable": {"thread_id": session_id}}
    try:
        snapshot = graph.get_state(config)
        if not snapshot or not hasattr(snapshot, "values"):
            return []

        messages = snapshot.values.get("messages", [])
        result = []
        for msg in messages:
            role = normalize_message_role(getattr(msg, "type", ""))
            content = normalize_message_text(getattr(msg, "content", ""))
            if content.startswith("**Internal Assessment State:**"):
                continue
            result.append({"role": role, "content": content})
        return result
    except Exception as exc:
        print(f"Error reading agent messages: {exc}")
        return []


def get_session_or_404(db: Session, session_id: str, user_id: str) -> Interview_Session:
    session_uuid, user_uuid = parse_session_and_user_ids(session_id, user_id)
    return get_session_row(db, session_uuid, user_uuid)


def load_problem_context(db: Session, session_row: Interview_Session) -> tuple[str, dict]:
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


def get_latest_code(db: Session, session_id: uuid.UUID) -> str:
    latest = db.exec(
        select(Session_Code_State)
        .where(Session_Code_State.session_id == session_id)
        .order_by(Session_Code_State.created_at.desc())
        .limit(1)
    ).first()
    return latest.code if latest else ""


def build_initial_state(
    payload: AgentInitRequest,
    problem_statement: str,
    problem_references: dict,
) -> InterviewAgentState:
    starter_message = payload.message or "Start the interview"
    return {
        "session_id": str(payload.session_id),
        "messages": [HumanMessage(content=starter_message)],
        "phase": InterviewPhase.PROBLEM_DISCUSSION.value,
        "problem_statement": problem_statement,
        "problem_references": problem_references,
        "execution_attempts": 0,
        "discussion_turns": 0,
        "review_turns": 0,
        "coding_turns": 0,
    }


def persist_turn_data(
    payload: PhaseRequest | AgentInitRequest,
    user_id: str,
    res: dict,
):
    with Session(engine) as db:
        session_row = get_session_or_404(db, payload.session_id, user_id)

        code = getattr(payload, "code", None)
        if code is not None:
            db.add(
                Session_Code_State(
                    session_id=session_row.session_id,
                    code=code,
                    language=getattr(payload, "language", ""),
                )
            )

        new_phase = res.get("phase")
        if new_phase:
            if new_phase == InterviewPhase.FEEDBACK and session_row.phase != InterviewPhase.FEEDBACK:
                session_row.status = "CLOSED"
                populate_total_time_spent_sec(session_row.session_id, user_id)
            session_row.phase = new_phase

            if new_phase == InterviewPhase.FEEDBACK:
                fb = res.get("feedback")
                if fb:
                    fb_dict = fb.model_dump() if hasattr(fb, "model_dump") else fb
                    final_score = None
                    if isinstance(fb_dict, dict):
                        final_score = fb_dict.get("overall_score")
                        if final_score is None:
                            session_summary = fb_dict.get("session_summary")
                            if isinstance(session_summary, dict):
                                final_score = session_summary.get("overall_score")
                    existing_fb = db.exec(
                        select(Session_Feedback)
                        .where(Session_Feedback.session_id == session_row.session_id)
                    ).first()
                    if existing_fb:
                        existing_fb.feedback_json = fb_dict
                        existing_fb.final_score = final_score
                        db.add(existing_fb)
                    else:
                        db.add(
                            Session_Feedback(
                                session_id=session_row.session_id,
                                feedback_json=fb_dict,
                                final_score=final_score
                            )
                        )

        db.add(session_row)
        db.commit()


def sync_runtime_state_before_turn(payload: PhaseRequest, graph):
    state_updates = {}

    if payload.code:
        state_updates["user_code"] = payload.code

    if payload.exit_clicked is not None:
        state_updates["exit_clicked"] = payload.exit_clicked

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


def sync_feedback_runtime_state(payload: PhaseRequest, graph, user_id: str):
    with Session(engine) as db:
        session_row = get_session_or_404(db, payload.session_id, user_id)

        populate_total_time_spent_sec(session_row.session_id, user_id)

        metrics = db.exec(
            select(Session_Metrics).where(Session_Metrics.session_id == session_row.session_id)
        ).first()

        state_updates = {}
        if metrics:
            state_updates["total_time_spent_sec"] = metrics.total_time_spent_sec or 0
            state_updates["total_submissions"] = metrics.total_submissions or 0
            state_updates["hints_used"] = metrics.hints_used or 0

        latest_code = get_latest_code(db, session_row.session_id)
        if latest_code:
            state_updates["user_code"] = latest_code

        if payload.time_expired is not None:
            state_updates["time_expired"] = payload.time_expired

        if payload.extra_time_used is not None:
            state_updates["extra_time_used"] = payload.extra_time_used

        if payload.extension_count is not None:
            state_updates["extension_count"] = payload.extension_count

        # Force session_ended_by to "TIMEOUT_END" to ensure all phase routers transition directly to FEEDBACK
        state_updates["session_ended_by"] = "TIMEOUT_END"

        if state_updates:
            config = {"configurable": {"thread_id": payload.session_id}}
            graph.update_state(config, state_updates)


def handle_timeout_action(graph, payload: TimeoutActionRequest) -> dict:
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



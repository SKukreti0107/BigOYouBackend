import uuid
from pydantic import BaseModel
from modules.db import (
    engine,
    InterviewPhase,
    Interview_Session,
    Problems,
    Problem_Reference,
    Session_Code_State,
    Session_Message,
)
from fastapi import APIRouter, Depends, HTTPException, status
from helpers.get_session_data import parse_session_and_user_ids, get_session_row,get_session_timer
from helpers.auth_deps import get_current_user
from helpers.populate_sesson_metrics import populate_total_time_spent_sec
from sqlmodel import Session, select
from services.ai_agent.agent import agent, Context
from datetime import timedelta

router = APIRouter()


class PhaseRequest(BaseModel):
    session_id: str
    message: str
    code: str | None = None
    language: str | None = None


class AgentInitRequest(BaseModel):
    session_id: str
    message: str | None = "Hi"


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


def _build_message_history(db: Session, session_id: uuid.UUID, user_message: str) -> list[dict]:
    history = db.exec(
        select(Session_Message)
        .where(Session_Message.session_id == session_id)
        .order_by(Session_Message.created_at)
    ).all()

    messages = [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": user_message})
    return messages


def _get_latest_code(db: Session, session_id: uuid.UUID) -> str:
    latest = db.exec(
        select(Session_Code_State)
        .where(Session_Code_State.session_id == session_id)
        .order_by(Session_Code_State.created_at.desc())
        .limit(1)
    ).first()
    return latest.code if latest else ""


def _persist_messages(
    db: Session,
    session_id: uuid.UUID,
    phase: InterviewPhase,
    user_message: str,
    agent_message: str,
):
    db.add(
        Session_Message(
            session_id=session_id,
            role="user",
            content=user_message,
            phase=phase,
        )
    )
    db.add(
        Session_Message(
            session_id=session_id,
            role="ai",
            content=agent_message,
            phase=phase,
        )
    )


def _run_phase(
    phase: InterviewPhase,
    payload: PhaseRequest,
    user_id: str,
    close_session: bool = False,
):
    with Session(engine) as db:
        session_row = _get_session_or_404(db, payload.session_id, user_id)
        session_row.phase = phase
        if close_session:
            session_row.status = "CLOSED"

        if payload.code:
            db.add(
                Session_Code_State(
                    session_id=session_row.session_id,
                    code=payload.code,
                    language=payload.language or "",
                )
            )

        problem_statement, problem_references = _load_problem_context(db, session_row)
        if phase == InterviewPhase.PROBLEM_DISCUSSION:
            user_code = ""
        else:
            if phase==InterviewPhase.REVIEW:
                ## stop the timer from backend and store total_time in metrics
                populate_total_time_spent_sec(session_row.session_id, user_id)


            user_code = payload.code or _get_latest_code(db, session_row.session_id)

        # Only pass the new user message; checkpointer accumulates history via thread_id
        response = agent.invoke(
            {"messages": [{"role": "user", "content": payload.message}]},
            config={"configurable": {"thread_id": str(session_row.session_id)}},
            context=Context(
                session_phase=phase.value,
                problem_statement=problem_statement,
                problem_references=problem_references,
                user_code=user_code,
            ),
        )

        structured = response.get("structured_response")
        if structured is None:
            agent_text = str(response)
        else:
            agent_text = getattr(structured, "response", str(structured))

        _persist_messages(
            db,
            session_row.session_id,
            phase,
            payload.message,
            agent_text,
        )
        db.add(session_row)
        db.commit()

        return structured

@router.post("/interview/agent_init")
def agent_init(payload: AgentInitRequest, user_id: str = Depends(get_current_user)):
    with Session(engine) as db:
        session_row = _get_session_or_404(db, payload.session_id, user_id)
        session_row.phase = InterviewPhase.PROBLEM_DISCUSSION

        problem_statement, problem_references = _load_problem_context(db, session_row)
        user_message = payload.message or "Hi"

        # Only pass the new user message; checkpointer accumulates history via thread_id
        response = agent.invoke(
            {"messages": [{"role": "user", "content": user_message}]},
            config={"configurable": {"thread_id": str(session_row.session_id)}},
            context=Context(
                session_phase=InterviewPhase.PROBLEM_DISCUSSION.value,
                problem_statement=problem_statement,
                problem_references=problem_references,
                user_code="",
            ),
        )

        structured = response.get("structured_response")
        if structured is None:
            agent_text = str(response)
        else:
            agent_text = getattr(structured, "response", str(structured))

        _persist_messages(
            db,
            session_row.session_id,
            InterviewPhase.PROBLEM_DISCUSSION,
            user_message,
            agent_text,
        )
        db.add(session_row)
        db.commit()

        return structured

@router.post("/interview/problem_discussion")
def problem_discussion(payload: PhaseRequest, user_id: str = Depends(get_current_user)):
    return _run_phase(InterviewPhase.PROBLEM_DISCUSSION, payload, user_id)


@router.post("/interview/coding")
def coding(payload: PhaseRequest, user_id: str = Depends(get_current_user)):
    return _run_phase(InterviewPhase.CODING, payload, user_id)


@router.post("/interview/review")
def review(payload: PhaseRequest, user_id: str = Depends(get_current_user)):
    return _run_phase(InterviewPhase.REVIEW, payload, user_id)


@router.post("/interview/feedback")
def feedback(payload: PhaseRequest, user_id: str = Depends(get_current_user)):
    return _run_phase(InterviewPhase.FEEDBACK, payload, user_id, close_session=True)

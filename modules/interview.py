import uuid
from modules.db import engine,Problems,Problem_topics,User_Problem_Status,Interview_Session
from fastapi import APIRouter,HTTPException,Response,Depends
from helpers.auth_deps import get_current_user
from helpers.get_session_data import (
    get_session_overview,
    get_session_messages,
    get_session_code_states,
    get_session_metrics,
    get_session_feedback,
)
from sqlmodel import Session,select
from sqlalchemy import func
from datetime import datetime,timezone

router = APIRouter()


@router.get("/interview/session")
def session_overview(session_id: str, user_id: str = Depends(get_current_user)):
    return get_session_overview(session_id, user_id)


@router.get("/interview/session/messages")
def session_messages(session_id: str, user_id: str = Depends(get_current_user)):
    return get_session_messages(session_id, user_id)


@router.get("/interview/session/code_states")
def session_code_states(session_id: str, user_id: str = Depends(get_current_user)):
    return get_session_code_states(session_id, user_id)


@router.get("/interview/session/metrics")
def session_metrics(session_id: str, user_id: str = Depends(get_current_user)):
    return get_session_metrics(session_id, user_id)


@router.get("/interview/session/feedback")
def session_feedback(session_id: str, user_id: str = Depends(get_current_user)):
    return get_session_feedback(session_id, user_id)


@router.post("/interview/start")
def start_interview(topic:str,user_id:str=Depends(get_current_user)):
    try:
        user_id = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400,detail="Invalid user_id")
    
    with Session(engine) as session:
        statement =(
            select(Problems)
            .join(Problem_topics, Problem_topics.problem_id == Problems.problem_id)
            .outerjoin(
                User_Problem_Status,
                (User_Problem_Status.problem_id == Problems.problem_id)
                & (User_Problem_Status.user_id == user_id),
            )
            .where(Problem_topics.topic == topic)
            .where(
                (User_Problem_Status.is_completed == False)  # noqa: E712
                | (User_Problem_Status.is_completed.is_(None))
            )
            .order_by(func.random())
            .limit(1)
        )

        problem = session.exec(statement).first()
        if not problem:
            raise HTTPException(status_code=404,detail="No unsolved problems found")
        
        session_row = Interview_Session(
            user_id=user_id,
            problem_id=problem.problem_id,
            topic=topic,
            started_at=datetime.now(timezone.utc),
            is_active=True,
            phase="PROBLEM_DISCUSSION"
        )

        session.add(session_row)
        session.commit()
        session.refresh(session_row)

        return {
            "session_id": str(session_row.session_id),
            "topic": topic,
            "problem": {
                "problem_id": str(problem.problem_id),
                "title": problem.title,
                "statement": problem.statement,
                "example": problem.example,
                "difficulty": problem.difficulty,
                "expected_time": problem.expected_time,
            },
        }
import uuid
from sqlmodel import Session, select
from sqlalchemy import func
from modules.db import (
    Interview_Session,
    Problems,
    Session_Feedback,
)


def fetch_sessions_history(
    db: Session,
    user_id: uuid.UUID,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[dict], int]:
    offset = (page - 1) * page_size
    total = db.exec(
        select(
            func.count(Interview_Session.session_id)
        )
        .where(Interview_Session.user_id == user_id)
    ).one()
    
    stmt = (
        select(
            Interview_Session.session_id.label("id"),
            Problems.title.label("Problem"),
            Interview_Session.topic.label("Topic"),
            Problems.difficulty.label("Difficulty"),
            Session_Feedback.final_score.label("Score"),
            Session_Feedback.created_at.label("Date"),
        )
        .join(Problems, Interview_Session.problem_id == Problems.problem_id)
        .join(Session_Feedback, Interview_Session.session_id == Session_Feedback.session_id)
        .where(Interview_Session.user_id == user_id)
        .order_by(Session_Feedback.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    result = db.exec(stmt).all()
    return [dict(row._mapping) for row in result], total

#returns last interview feedback -> strengths and weaknesses
def fetch_last_interview_feedback(db: Session, session_id: uuid.UUID) -> dict:
    stmt = (
        select(
            Session_Feedback.feedback_json
        )
        .where(Session_Feedback.session_id == session_id)
        .order_by(Session_Feedback.created_at.desc())
        .limit(1)
    )
    res = db.exec(stmt).first()
    result = {
        "strengths": res.get("strengths", []),
        "weaknesses": res.get("weaknesses", [])
    } 
    return result if result else {}

# write code to make on payload for dashboard api endpoint

# 1. payload for last interview feedback -> strengths and weaknesses
from modules.db import engine, Session_Feedback, Interview_Session
from sqlmodel import Session, select
import uuid


def fetch_last_interview_feedback(user_id: str) -> dict:
    try:
        user_uuid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return {}

    stmt = (
        select(Session_Feedback.feedback_json)
        .join(Interview_Session, Interview_Session.session_id == Session_Feedback.session_id)
        .where(Interview_Session.user_id == user_uuid)
        .order_by(Session_Feedback.created_at.desc())
        .limit(1)
    )

    with Session(engine) as db:
        feedback = db.exec(stmt).first()

        if not feedback:
            return {}

        feedback_json = feedback[0] if isinstance(feedback, tuple) else feedback

        return {
            "strengths": feedback_json.get("strengths", []),
            "weaknesses": feedback_json.get("weaknesses", []),
            "score": feedback_json.get("overall_score", 0)
        }

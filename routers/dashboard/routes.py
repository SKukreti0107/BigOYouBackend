from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from modules.db import engine
from .service import (
    calculate_streak,
    fetch_quick_stats,
    fetch_score_trend,
    fetch_weak_areas,
    fetch_last_interview_feedback
)
import uuid

router = APIRouter()

@router.get("/dashboard")
async def get_dashboard(user_id: str):
    try:
        user_uuid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid user_id format")

    with Session(engine) as db:
        streak = calculate_streak(db, user_uuid)
        quick_stats = fetch_quick_stats(db, user_uuid)
        score_trend = fetch_score_trend(db, user_uuid)
        weak_areas = fetch_weak_areas(db, user_uuid)
        last_interview_feedback = fetch_last_interview_feedback(db, user_uuid)

        return {
            "streak": streak,
            "quick_stats": quick_stats,
            "score_trend": score_trend,
            "weak_areas": weak_areas,
            "last_interview_feedback": last_interview_feedback
        }

from fastapi import APIRouter, Depends
from sqlmodel import Session
from .service import fetch_last_interview_feedback
import uuid 
router = APIRouter()


@router.get("/dashboard")
async def get_dashboard(user_id:str):
    dashboard_payload = {}
    dashboard_payload["last_interview_feedback"] = fetch_last_interview_feedback(user_id)
    return dashboard_payload



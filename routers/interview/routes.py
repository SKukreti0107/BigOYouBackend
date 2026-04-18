from fastapi import APIRouter, HTTPException, Depends

from helpers.auth.auth_deps import get_current_user
from helpers.session.get_session_data import (
    get_session_overview,
    get_session_messages,
    get_session_code_states,
    get_session_metrics,
    get_session_feedback,
    get_session_timer,
)
from .service import get_session_timer_with_extensions, start_interview_for_topic


router = APIRouter()


@router.post("/interview/session/timer")
def session_timer(session_id: str, user_id: str = Depends(get_current_user)):
    payload = get_session_timer(session_id, user_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Session timer not found")

    remaining_time = get_session_timer_with_extensions(session_id, user_id, payload)
    if remaining_time is None:
        raise HTTPException(status_code=404, detail="Session timer not found")

    return remaining_time


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
def start_interview(topic: str, user_id: str = Depends(get_current_user)):
    return start_interview_for_topic(topic, user_id)
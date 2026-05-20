from fastapi import APIRouter, Depends
from sqlmodel import Session
from modules.db import engine
from helpers.auth.auth_deps import get_current_user
from helpers.session.history import fetch_sessions_history
from helpers.session.get_session_data import fetch_last_session_id
import uuid

router = APIRouter()


@router.get("/history")
# Returns the user's session history with pagination support
def get_sessions_history(
    user_id: uuid.UUID = Depends(get_current_user),
    page: int = 1,
    page_size: int = 10,
):
    try:
        with Session(engine) as db:
            sessions, total = fetch_sessions_history(db, user_id, page, page_size)
            return {"sessions": sessions, "total": total}
    except Exception as e:
        return {"error": str(e)}


@router.get("/last_session_id")
def get_last_session_id(user_id: uuid.UUID = Depends(get_current_user)):
    try:
        last_session_id = fetch_last_session_id(user_id)
        return {"last_session_id": last_session_id}
    except Exception as e:
        return {"error": str(e)}
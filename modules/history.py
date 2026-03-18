from fastapi import APIRouter,Depends
from sqlmodel import Session 
from helpers.auth_deps import get_current_user
from helpers.get_session_data import get_all_sessions
router = APIRouter()


# @router.post("/sessions_history")
# def all_user_sessions(user_id:str = Depends(get_current_user)):
#     get_all_sessions(user_id)


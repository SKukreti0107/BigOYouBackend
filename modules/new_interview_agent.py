import uuid
from typing import Literal
from pydantic import BaseModel
from modules.db import (
    engine,
    InterviewPhase,
    Interview_Session,
    Problems,
    Problem_Reference,
    Session_Code_State,
    Session_Message,
    Session_Feedback,
    Session_Metrics,
)
from fastapi import APIRouter, Depends, HTTPException, status
from helpers.get_session_data import parse_session_and_user_ids, get_session_row,get_session_timer
from helpers.auth_deps import get_current_user
from helpers.populate_sesson_metrics import populate_total_time_spent_sec
from sqlmodel import Session, select
from services.ai_agent.agent import phase_agents, Context, FeedbackContext
from services.ai_agent.schemas import InterviewAgentState
from datetime import timedelta
from langchain_core.messages import HumanMessage
from services.ai_agent.langgraph_agent import graph
from services.ai_agent.helpers.agent_runners import run_interview_turn,get_last_ai_message
router = APIRouter()


#-------------------------------------------------------------------
#Schemas and helpers 
class PhaseRequest(BaseModel):
    session_id: str
    message: str
    code: str | None = None
    language: str | None = None
    role: Literal["user", "system"] = "user"


class AgentInitRequest(BaseModel):
    session_id: str
    message: str | None = "[SYSTEM EVENT] Start the interview"
    role: Literal["user", "system"] = "system"


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

def _get_latest_code(db: Session, session_id: uuid.UUID) -> str:
    latest = db.exec(
        select(Session_Code_State)
        .where(Session_Code_State.session_id == session_id)
        .order_by(Session_Code_State.created_at.desc())
        .limit(1)
    ).first()
    return latest.code if latest else ""


def invoke_agent(
    state:InterviewAgentState,
    payload: PhaseRequest,
    user_id: str,
    close_session: bool = False,
):
    with Session(engine) as db:
        session_row = _get_session_or_404(db, payload.session_id, user_id)
        session_row.phase = state.get("phase") 
        if close_session:
            session_row.status = "CLOSED"

        if payload.code:
            state['user_code']=payload.code
            db.add(
                Session_Code_State(
                    session_id=session_row.session_id,
                    code=payload.code,
                    language=payload.language or "",
                )
            )


#-------------------------------------------------------------------
#routers
@router.post("/interview/agent_init")
def agent_init(payload: AgentInitRequest, user_id: str = Depends(get_current_user)):
    with Session(engine) as db:
        session_row = _get_session_or_404(db, payload.session_id, user_id)
        problem_statement, problem_references = _load_problem_context(db, session_row)
        #build graph state
        state:InterviewAgentState = {
            "session_id": str(payload.session_id),
            "messages": [HumanMessage(content=payload.message)],
            "phase": "PROBLEM_DISCUSSION",
            "problem_statement": problem_statement,
            "problem_references": problem_references,
            "execution_attempts": 0,
            "discussion_turns": 0,
            "review_turns": 0,
            "coding_turns": 0,
        }
        session_row.phase = InterviewPhase.PROBLEM_DISCUSSION

        res = run_interview_turn(graph=graph,state=state,thread_id=payload.session_id,user_input=payload.message,is_first=True)
        #send phase to the FE too
        return res
    

@router.post("/interview/problem_discussion")
def problem_discussion(payload: PhaseRequest, user_id: str = Depends(get_current_user)):
    return run_interview_turn(graph=graph,thread_id=payload.session_id,user_input=payload.message)


@router.post("/interview/coding")
def coding(payload: PhaseRequest, user_id: str = Depends(get_current_user)):
    return run_interview_turn(graph=graph,thread_id=payload.session_id,user_input=payload.message)



@router.post("/interview/review")
def review(payload: PhaseRequest, user_id: str = Depends(get_current_user)):
    return run_interview_turn(graph=graph,thread_id=payload.session_id,user_input=payload.message)



@router.post("/interview/feedback")
def feedback(payload: PhaseRequest, user_id: str = Depends(get_current_user)):
    return run_interview_turn(graph=graph,thread_id=payload.session_id,user_input=payload.message)


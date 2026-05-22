from fastapi import APIRouter, Depends, HTTPException, Request, status, File, UploadFile
from sqlmodel import Session
import httpx
import os

from helpers.auth.auth_deps import get_current_user
from modules.db import engine
from modules.schemas import PhaseRequest, AgentInitRequest, TimeoutActionRequest
from services.ai_agent.langgraph_agent import get_graph, clear_agent_checkpoints
from services.ai_agent.helpers.agent_runners import run_interview_turn

from .service import (
    build_initial_state,
    get_agent_messages,
    get_session_or_404,
    handle_timeout_action,
    load_problem_context,
    persist_turn_data,
    sync_feedback_runtime_state,
    sync_runtime_state_before_turn,
)


router = APIRouter()


def _get_graph_or_503(request: Request):
    if not getattr(request.app.state, "ai_agent_available", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI agent service unavailable",
        )
    try:
        return get_graph()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI agent service unavailable",
        ) from exc


@router.get("/interview/agent_messages")
def agent_messages(
    session_id: str,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    graph = _get_graph_or_503(request)
    return get_agent_messages(graph, session_id)


@router.post("/interview/timeout_action")
def timeout_action(
    payload: TimeoutActionRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    graph = _get_graph_or_503(request)
    with Session(engine) as db:
        get_session_or_404(db, payload.session_id, user_id)

    return handle_timeout_action(graph, payload)


@router.post("/interview/agent_init")
def agent_init(
    payload: AgentInitRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    graph = _get_graph_or_503(request)
    with Session(engine) as db:
        session_row = get_session_or_404(db, payload.session_id, user_id)
        problem_statement, problem_references = load_problem_context(db, session_row)

    state = build_initial_state(payload, problem_statement, problem_references)
    res = run_interview_turn(
        graph=graph,
        state=state,
        thread_id=payload.session_id,
        user_input=payload.message,
        is_first=True,
    )
    persist_turn_data(payload, user_id, res)
    return res


@router.post("/interview/problem_discussion")
def problem_discussion(
    payload: PhaseRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    graph = _get_graph_or_503(request)
    sync_runtime_state_before_turn(payload, graph)
    res = run_interview_turn(graph=graph, thread_id=payload.session_id, user_input=payload.message)
    persist_turn_data(payload, user_id, res)
    return res


@router.post("/interview/coding")
def coding(
    payload: PhaseRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    graph = _get_graph_or_503(request)
    sync_runtime_state_before_turn(payload, graph)
    res = run_interview_turn(graph=graph, thread_id=payload.session_id, user_input=payload.message)
    persist_turn_data(payload, user_id, res)
    return res


@router.post("/interview/review")
def review(
    payload: PhaseRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    graph = _get_graph_or_503(request)
    sync_runtime_state_before_turn(payload, graph)
    res = run_interview_turn(graph=graph, thread_id=payload.session_id, user_input=payload.message)
    persist_turn_data(payload, user_id, res)
    return res


@router.post("/interview/feedback")
def feedback(
    payload: PhaseRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    graph = _get_graph_or_503(request)
    sync_feedback_runtime_state(payload, graph, user_id)

    res = run_interview_turn(graph=graph, thread_id=payload.session_id, user_input=payload.message)
    persist_turn_data(payload, user_id, res)
    clear_agent_checkpoints(payload.session_id)
    return res


#router to end intereview 
@router.post("/interview/end")
def end_interview(
    payload: PhaseRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    graph = _get_graph_or_503(request)
    sync_runtime_state_before_turn(payload, graph)
    res = run_interview_turn(graph=graph, thread_id=payload.session_id, user_input=payload.message)
    persist_turn_data(payload, user_id, res)
    clear_agent_checkpoints(payload.session_id)

    with Session(engine) as db:
        from helpers.session.end_interview_session import set_session_terminated
        termination_complete = set_session_terminated(db, payload.session_id)
        if not termination_complete:
            print(f"Warning: could not set session {payload.session_id} as terminated in DB")

        db.commit()

    return res


@router.post("/interview/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """
    Transcribes audio recorded by the frontend using Groq's Whisper API.
    """
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Groq API key not configured on backend"
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty audio file received"
        )

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {groq_api_key}"
    }

    # Whisper expects a filename parameter to detect format (e.g. input.webm)
    filename = file.filename if file.filename else "input.webm"
    files = {
        "file": (filename, content, file.content_type or "audio/webm")
    }
    data = {
        "model": "whisper-large-v3",
        "response_format": "json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=headers,
                files=files,
                data=data,
                timeout=30.0
            )

        if response.status_code != 200:
            print(f"Groq API error response: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail="Groq Whisper transcription API failed"
            )

        return response.json()

    except httpx.RequestError as exc:
        print(f"HTTP request to Groq failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect to Groq Whisper transcription API"
        )
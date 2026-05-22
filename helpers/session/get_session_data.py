from modules.db import Problems
import uuid
from fastapi import Depends, HTTPException, status
from modules.db import (
	engine,
	Interview_Session,
	Session_Metrics,
	Session_Code_State,
	Session_Message,
	Session_Feedback,
)
from helpers.auth.auth_deps import get_current_user
from sqlmodel import Session, select
from datetime import timedelta,datetime


def parse_session_and_user_ids(session_id: str | uuid.UUID, user_id: str | uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
	try:
		session_uuid = session_id if isinstance(session_id, uuid.UUID) else uuid.UUID(session_id)
		user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(user_id)
	except (ValueError, AttributeError):
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Invalid session_id or user_id",
		)

	return session_uuid, user_uuid


def get_session_row(db: Session, session_uuid: uuid.UUID, user_uuid: uuid.UUID) -> Interview_Session:
	session_stmt = select(Interview_Session).where(
		(Interview_Session.session_id == session_uuid)
		& (Interview_Session.user_id == user_uuid)
	)
	session_row = db.exec(session_stmt).first()
	if not session_row:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Session not found",
		)

	return session_row

	

def fetch_session_overview(session_row: Interview_Session, problem_row: Problems = None) -> dict:
	overview = {
		"session_id": str(session_row.session_id),
		"user_id": str(session_row.user_id),
		"problem_id": str(session_row.problem_id),
		"topic": session_row.topic,
		"started_at": session_row.started_at,
		"status": session_row.status,
		"phase": session_row.phase,
	}
	if problem_row:
		overview["problem"] = {
			"problem_id": str(problem_row.problem_id),
			"title": problem_row.title,
			"statement": problem_row.statement,
			"example": problem_row.example,
			"difficulty": problem_row.difficulty,
			"expected_time": problem_row.expected_time,
		}
	return overview


def fetch_session_messages(db: Session, session_uuid: uuid.UUID) -> list[dict]:
	messages = db.exec(
		select(Session_Message)
		.where(Session_Message.session_id == session_uuid)
		.order_by(Session_Message.created_at)
	).all()

	return [
		{
			"message_id": str(m.message_id),
			"session_id": str(m.session_id),
			"role": m.role,
			"content": m.content,
			"phase": m.phase,
			"created_at": m.created_at,
		}
		for m in messages
	]


def fetch_session_code_states(db: Session, session_uuid: uuid.UUID) -> list[dict]:
	code_states = db.exec(
		select(Session_Code_State)
		.where(Session_Code_State.session_id == session_uuid)
		.order_by(Session_Code_State.created_at)
	).all()

	return [
		{
			"snapshot_id": str(s.snapshot_id),
			"session_id": str(s.session_id),
			"code": s.code,
			"language": s.language,
			"created_at": s.created_at,
		}
		for s in code_states
	]


def fetch_session_metrics(db: Session, session_uuid: uuid.UUID) -> dict | None:
	metrics = db.exec(
		select(Session_Metrics)
		.where(Session_Metrics.session_id == session_uuid)
	).first()

	if not metrics:
		return None

	return {
		"session_id": str(metrics.session_id),
		"total_time_spent_sec": metrics.total_time_spent_sec,
		"time_to_first_submission_sec": metrics.time_to_first_submission_sec,
		"total_submissions": metrics.total_submissions,
		"hints_used": metrics.hints_used,
		"updated_at": metrics.updated_at,
	}


def fetch_session_feedback(db: Session, session_uuid: uuid.UUID) -> dict | None:
	feedback = db.exec(
		select(Session_Feedback)
		.where(Session_Feedback.session_id == session_uuid)
	).first()

	if not feedback:
		return None

	return {
		"session_id": str(feedback.session_id),
		"feedback": feedback.feedback_json,
		"created_at": feedback.created_at,
	}

def fetch_session_timer(db: Session, session_uuid: uuid.UUID) -> dict | None:
	result = db.exec(
		select(Interview_Session, Problems)
		.where(Interview_Session.session_id == session_uuid)
		.join(Problems, Interview_Session.problem_id == Problems.problem_id)
	).first()

	if not result:
		return None

	session_row, problem_row = result

	# Load extension count from LangGraph state checkpointer if available
	extension_count = 0
	session_ended_by = ""
	try:
		from services.ai_agent.langgraph_agent import is_agent_available, get_graph
		if is_agent_available():
			graph = get_graph()
			config = {"configurable": {"thread_id": str(session_uuid)}}
			snapshot = graph.get_state(config)
			if snapshot and hasattr(snapshot, "values"):
				extension_count = int(snapshot.values.get("extension_count") or 0)
				session_ended_by = snapshot.values.get("session_ended_by") or ""
	except Exception as exc:
		print(f"Error loading extension_count from LangGraph state: {exc}")

	from datetime import timezone
	started_at = session_row.started_at
	if started_at.tzinfo is None:
		started_at = started_at.replace(tzinfo=timezone.utc)

	now = datetime.now(timezone.utc)
	total_expected_minutes = problem_row.expected_time + extension_count * 15

	if session_ended_by == "TIMEOUT_END":
		remaining_seconds = 0.0
	else:
		remaining_time = started_at + timedelta(minutes=total_expected_minutes) - now
		remaining_seconds = remaining_time.total_seconds()

	return {
		"remaining_time": remaining_seconds,
		"phase": session_row.phase,
		"status": session_row.status,
		"expected_time": total_expected_minutes
	}


def get_session_overview(session_id: str, user_id: str = Depends(get_current_user)):
	with Session(engine) as db:
		session_uuid, user_uuid = parse_session_and_user_ids(session_id, user_id)
		session_row = get_session_row(db, session_uuid, user_uuid)
		problem_row = db.get(Problems, session_row.problem_id)
		return fetch_session_overview(session_row, problem_row)


def get_session_messages(session_id: str, user_id: str = Depends(get_current_user)):
	with Session(engine) as db:
		session_uuid, user_uuid = parse_session_and_user_ids(session_id, user_id)
		get_session_row(db, session_uuid, user_uuid)
		return fetch_session_messages(db, session_uuid)


def get_session_code_states(session_id: str, user_id: str = Depends(get_current_user)):
	with Session(engine) as db:
		session_uuid, user_uuid = parse_session_and_user_ids(session_id, user_id)
		get_session_row(db, session_uuid, user_uuid)
		return fetch_session_code_states(db, session_uuid)


def get_session_metrics(session_id: str, user_id: str = Depends(get_current_user)):
	with Session(engine) as db:
		session_uuid, user_uuid = parse_session_and_user_ids(session_id, user_id)
		get_session_row(db, session_uuid, user_uuid)
		return fetch_session_metrics(db, session_uuid)


def get_session_feedback(session_id: str, user_id: str = Depends(get_current_user)):
	with Session(engine) as db:
		session_uuid, user_uuid = parse_session_and_user_ids(session_id, user_id)
		get_session_row(db, session_uuid, user_uuid)
		return fetch_session_feedback(db, session_uuid)

def get_session_timer(session_id: str, user_id: str = Depends(get_current_user)):
	with Session(engine) as db:
		session_uuid, user_uuid = parse_session_and_user_ids(session_id, user_id)
		get_session_row(db, session_uuid, user_uuid)
		return fetch_session_timer(db, session_uuid)

def get_session_data(session_id: str, user_id: str = Depends(get_current_user)):
	return {
		"session": get_session_overview(session_id, user_id),
		"messages": get_session_messages(session_id, user_id),
		"code_states": get_session_code_states(session_id, user_id),
		"metrics": get_session_metrics(session_id, user_id),
		"feedback": get_session_feedback(session_id, user_id),
	}

def fetch_last_session_id(user_id: uuid.UUID = Depends(get_current_user)):
	with Session(engine) as db:
		query = select(Interview_Session.session_id).where(Interview_Session.user_id == user_id).order_by(Interview_Session.user_id.desc()).limit(1)
		result = db.execute(query).scalar_one_or_none()
		if result:
			return result
		return None

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from modules.db import engine, Problems, Problem_topics, User_Problem_Status, Interview_Session, Session_Metrics


def get_session_timer_with_extensions(session_id: str, user_id: str, base_timer: dict | None) -> int | None:
    if not base_timer:
        return None

    try:
        from services.ai_agent.langgraph_agent import get_graph

        graph = get_graph()
        config = {"configurable": {"thread_id": session_id}}
        snapshot = graph.get_state(config)
        values = snapshot.values if snapshot and hasattr(snapshot, "values") else {}

        if (values.get("session_ended_by") or "") == "TIMEOUT_END":
            return 0

        extension_count = int(values.get("extension_count") or 0)
        if extension_count > 0:
            base_timer["remaining_time"] = base_timer["remaining_time"] + extension_count * 15 * 60
    except Exception:
        pass

    return base_timer["remaining_time"]


def start_interview_for_topic(
    topic: str, user_id: str, problem_id: str | None = None
) -> dict:
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id")

    with Session(engine) as session:
        if problem_id:
            try:
                prob_uuid = uuid.UUID(problem_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid problem_id")
            statement = select(Problems).where(Problems.problem_id == prob_uuid)
            problem = session.exec(statement).first()
            if not problem:
                raise HTTPException(status_code=404, detail="Problem not found")
        else:
            statement = (
                select(Problems)
                .join(Problem_topics, Problem_topics.problem_id == Problems.problem_id)
                .outerjoin(
                    User_Problem_Status,
                    (User_Problem_Status.problem_id == Problems.problem_id)
                    & (User_Problem_Status.user_id == user_uuid),
                )
                .where(Problem_topics.topic == topic)
                .where(
                    (User_Problem_Status.is_completed == False)
                    | (User_Problem_Status.is_completed.is_(None))
                )
                .order_by(func.random())
                .limit(1)
            )

            problem = session.exec(statement).first()
            if not problem:
                raise HTTPException(status_code=404, detail="No unsolved problems found")

        session_row = Interview_Session(
            user_id=user_uuid,
            problem_id=problem.problem_id,
            topic=topic,
            started_at=datetime.now(timezone.utc),
            is_active=True,
            phase="PROBLEM_DISCUSSION",
        )

        session_metrics_row = Session_Metrics(
            session_id=session_row.session_id,
        )

        session.add(session_row)
        session.add(session_metrics_row)
        session.commit()
        session.refresh(session_row)
        session.refresh(session_metrics_row)

        return {
            "session_id": str(session_row.session_id),
            "topic": topic,
            "problem": {
                "problem_id": str(problem.problem_id),
                "title": problem.title,
                "statement": problem.statement,
                "example": problem.example,
                "difficulty": problem.difficulty,
                "expected_time": problem.expected_time,
            },
        }
    

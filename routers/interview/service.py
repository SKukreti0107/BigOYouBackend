import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from modules.db import engine, Problems, Problem_topics, User_Problem_Status, Interview_Session, Session_Metrics, Session_Feedback


def get_session_timer_with_extensions(session_id: str, user_id: str, base_timer: dict | None) -> int | None:
    if not base_timer:
        return None
    return int(base_timer.get("remaining_time", 0))


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
            # 1. Get all problem_ids completed by the user (closed sessions with score > 70)
            completed_problems_subquery = (
                select(Interview_Session.problem_id)
                .join(Session_Feedback, Session_Feedback.session_id == Interview_Session.session_id)
                .where(Interview_Session.user_id == user_uuid)
                .where(Interview_Session.status == "CLOSED")
                .where(Session_Feedback.final_score > 70)
            )

            # 2. Query unsolved/uncompleted problems in this topic
            statement = (
                select(Problems)
                .join(Problem_topics, Problem_topics.problem_id == Problems.problem_id)
                .where(Problem_topics.topic == topic)
                .where(Problems.problem_id.notin_(completed_problems_subquery))
                .order_by(func.random())
                .limit(1)
            )

            problem = session.exec(statement).first()

            # 3. Fallback: If all problems in this topic are completed, pick any random problem from the topic to allow re-practice
            if not problem:
                fallback_statement = (
                    select(Problems)
                    .join(Problem_topics, Problem_topics.problem_id == Problems.problem_id)
                    .where(Problem_topics.topic == topic)
                    .order_by(func.random())
                    .limit(1)
                )
                problem = session.exec(fallback_statement).first()

            if not problem:
                raise HTTPException(status_code=404, detail="No problems found for this topic")

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
    

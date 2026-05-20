import uuid
from fastapi import APIRouter, HTTPException, Depends, status
from sqlmodel import Session, select, col

from helpers.auth.auth_deps import get_current_user
from modules.db import (
    engine,
    Users,
    Problems,
    Problem_topics,
    Problem_Reference,
    Interview_Session,
    Session_Feedback,
    Session_Metrics,
    Session_Message,
    Session_Code_State,
    User_Problem_Status,
)
from modules.schemas import (
    ProblemCreateRequest,
    ProblemUpdateRequest,
    ReferenceCreateRequest,
    ReferenceUpdateRequest,
)

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_EMAIL = "shubhamkukreti.0107@gmail.com"


# ── Admin Guard ──

def require_admin(user_id: str = Depends(get_current_user)):
    """Dependency that ensures the caller is the hardcoded admin."""
    with Session(engine) as db:
        user = db.get(Users, uuid.UUID(user_id))
        if not user or user.email != ADMIN_EMAIL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )
    return user_id


# ── Admin Check ──

@router.get("/check")
def admin_check(user_id: str = Depends(get_current_user)):
    with Session(engine) as db:
        user = db.get(Users, uuid.UUID(user_id))
        is_admin = user is not None and user.email == ADMIN_EMAIL
        return {"is_admin": is_admin}


# ═══════════════════════════════════════════════════════
#  PROBLEM CRUD
# ═══════════════════════════════════════════════════════

@router.get("/problems")
def list_problems(_admin: str = Depends(require_admin)):
    """List all problems with their topics and whether a reference exists."""
    with Session(engine) as db:
        problems = db.exec(select(Problems).order_by(Problems.title)).all()

        result = []
        for p in problems:
            topics = db.exec(
                select(Problem_topics.topic).where(Problem_topics.problem_id == p.problem_id)
            ).all()

            has_reference = db.exec(
                select(Problem_Reference.ref_id).where(Problem_Reference.problem_id == p.problem_id)
            ).first() is not None

            result.append({
                "problem_id": str(p.problem_id),
                "title": p.title,
                "statement": p.statement,
                "example": p.example,
                "difficulty": p.difficulty,
                "expected_time": p.expected_time,
                "topics": topics,
                "has_reference": has_reference,
            })

        return result


@router.get("/problems/{problem_id}")
def get_problem(problem_id: str, _admin: str = Depends(require_admin)):
    """Get a single problem with its topics and reference solution."""
    with Session(engine) as db:
        p = db.get(Problems, uuid.UUID(problem_id))
        if not p:
            raise HTTPException(404, "Problem not found")

        topics = db.exec(
            select(Problem_topics.topic).where(Problem_topics.problem_id == p.problem_id)
        ).all()

        ref = db.exec(
            select(Problem_Reference).where(Problem_Reference.problem_id == p.problem_id)
        ).first()

        ref_data = None
        if ref:
            ref_data = {
                "ref_id": str(ref.ref_id),
                "optimal_approach": ref.optimal_approach,
                "time_complexity": ref.time_complexity,
                "space_complexity": ref.space_complexity,
                "key_insights": ref.key_insights,
                "common_pitfalls": ref.common_pitfalls,
                "pseudocode": ref.pseudocode,
            }

        return {
            "problem_id": str(p.problem_id),
            "title": p.title,
            "statement": p.statement,
            "example": p.example,
            "difficulty": p.difficulty,
            "expected_time": p.expected_time,
            "topics": topics,
            "reference": ref_data,
        }


@router.post("/problems", status_code=201)
def create_problem(payload: ProblemCreateRequest, _admin: str = Depends(require_admin)):
    """Create a new problem with topics."""
    with Session(engine) as db:
        # Check duplicate title
        existing = db.exec(select(Problems).where(Problems.title == payload.title)).first()
        if existing:
            raise HTTPException(409, f"Problem with title '{payload.title}' already exists")

        problem = Problems(
            problem_id=uuid.uuid4(),
            title=payload.title,
            statement=payload.statement,
            example=payload.example,
            difficulty=payload.difficulty,
            expected_time=payload.expected_time,
        )
        db.add(problem)
        db.flush()  # Get the problem_id

        for topic_name in payload.topics:
            db.add(Problem_topics(problem_id=problem.problem_id, topic=topic_name.strip()))

        db.commit()

        return {"problem_id": str(problem.problem_id), "message": "Problem created"}


@router.put("/problems/{problem_id}")
def update_problem(problem_id: str, payload: ProblemUpdateRequest, _admin: str = Depends(require_admin)):
    """Update an existing problem and optionally replace its topics."""
    with Session(engine) as db:
        p = db.get(Problems, uuid.UUID(problem_id))
        if not p:
            raise HTTPException(404, "Problem not found")

        if payload.title is not None:
            # Check for duplicates (excluding self)
            dup = db.exec(
                select(Problems).where(Problems.title == payload.title, Problems.problem_id != p.problem_id)
            ).first()
            if dup:
                raise HTTPException(409, f"Another problem with title '{payload.title}' already exists")
            p.title = payload.title

        if payload.statement is not None:
            p.statement = payload.statement
        if payload.example is not None:
            p.example = payload.example
        if payload.difficulty is not None:
            p.difficulty = payload.difficulty
        if payload.expected_time is not None:
            p.expected_time = payload.expected_time

        # Replace topics if provided
        if payload.topics is not None:
            existing_topics = db.exec(
                select(Problem_topics).where(Problem_topics.problem_id == p.problem_id)
            ).all()
            for t in existing_topics:
                db.delete(t)
            for topic_name in payload.topics:
                db.add(Problem_topics(problem_id=p.problem_id, topic=topic_name.strip()))

        db.add(p)
        db.commit()

        return {"message": "Problem updated"}


@router.delete("/problems/{problem_id}")
def delete_problem(problem_id: str, _admin: str = Depends(require_admin)):
    """Delete a problem and cascade to topics, references, and related session data."""
    pid = uuid.UUID(problem_id)
    with Session(engine) as db:
        p = db.get(Problems, pid)
        if not p:
            raise HTTPException(404, "Problem not found")

        # Delete reference
        refs = db.exec(select(Problem_Reference).where(Problem_Reference.problem_id == pid)).all()
        for r in refs:
            db.delete(r)

        # Delete topics
        topics = db.exec(select(Problem_topics).where(Problem_topics.problem_id == pid)).all()
        for t in topics:
            db.delete(t)

        # Delete user_problem_status
        statuses = db.exec(select(User_Problem_Status).where(User_Problem_Status.problem_id == pid)).all()
        for s in statuses:
            db.delete(s)

        # Delete sessions and their children
        sessions = db.exec(select(Interview_Session).where(Interview_Session.problem_id == pid)).all()
        for sess in sessions:
            sid = sess.session_id
            for fb in db.exec(select(Session_Feedback).where(Session_Feedback.session_id == sid)).all():
                db.delete(fb)
            for m in db.exec(select(Session_Metrics).where(Session_Metrics.session_id == sid)).all():
                db.delete(m)
            for msg in db.exec(select(Session_Message).where(Session_Message.session_id == sid)).all():
                db.delete(msg)
            for cs in db.exec(select(Session_Code_State).where(Session_Code_State.session_id == sid)).all():
                db.delete(cs)
            db.delete(sess)

        db.delete(p)
        db.commit()

        return {"message": "Problem deleted"}


# ═══════════════════════════════════════════════════════
#  REFERENCE SOLUTION CRUD
# ═══════════════════════════════════════════════════════

@router.get("/problems/{problem_id}/reference")
def get_reference(problem_id: str, _admin: str = Depends(require_admin)):
    """Get the reference solution for a problem."""
    pid = uuid.UUID(problem_id)
    with Session(engine) as db:
        ref = db.exec(select(Problem_Reference).where(Problem_Reference.problem_id == pid)).first()
        if not ref:
            raise HTTPException(404, "No reference solution found for this problem")

        return {
            "ref_id": str(ref.ref_id),
            "problem_id": str(ref.problem_id),
            "optimal_approach": ref.optimal_approach,
            "time_complexity": ref.time_complexity,
            "space_complexity": ref.space_complexity,
            "key_insights": ref.key_insights,
            "common_pitfalls": ref.common_pitfalls,
            "pseudocode": ref.pseudocode,
        }


@router.post("/problems/{problem_id}/reference", status_code=201)
def create_reference(problem_id: str, payload: ReferenceCreateRequest, _admin: str = Depends(require_admin)):
    """Create a reference solution for a problem (upsert — replaces if exists)."""
    pid = uuid.UUID(problem_id)
    with Session(engine) as db:
        # Verify the problem exists
        p = db.get(Problems, pid)
        if not p:
            raise HTTPException(404, "Problem not found")

        # Delete existing reference if any (upsert behavior)
        existing = db.exec(select(Problem_Reference).where(Problem_Reference.problem_id == pid)).first()
        if existing:
            db.delete(existing)
            db.flush()

        ref = Problem_Reference(
            ref_id=uuid.uuid4(),
            problem_id=pid,
            optimal_approach=payload.optimal_approach,
            time_complexity=payload.time_complexity,
            space_complexity=payload.space_complexity,
            key_insights=payload.key_insights,
            common_pitfalls=payload.common_pitfalls,
            pseudocode=payload.pseudocode,
        )
        db.add(ref)
        db.commit()

        return {"ref_id": str(ref.ref_id), "message": "Reference solution saved"}


@router.put("/problems/{problem_id}/reference")
def update_reference(problem_id: str, payload: ReferenceUpdateRequest, _admin: str = Depends(require_admin)):
    """Update the reference solution for a problem."""
    pid = uuid.UUID(problem_id)
    with Session(engine) as db:
        ref = db.exec(select(Problem_Reference).where(Problem_Reference.problem_id == pid)).first()
        if not ref:
            raise HTTPException(404, "No reference solution found for this problem")

        if payload.optimal_approach is not None:
            ref.optimal_approach = payload.optimal_approach
        if payload.time_complexity is not None:
            ref.time_complexity = payload.time_complexity
        if payload.space_complexity is not None:
            ref.space_complexity = payload.space_complexity
        if payload.key_insights is not None:
            ref.key_insights = payload.key_insights
        if payload.common_pitfalls is not None:
            ref.common_pitfalls = payload.common_pitfalls
        if payload.pseudocode is not None:
            ref.pseudocode = payload.pseudocode

        db.add(ref)
        db.commit()

        return {"message": "Reference solution updated"}


@router.delete("/problems/{problem_id}/reference")
def delete_reference(problem_id: str, _admin: str = Depends(require_admin)):
    """Delete the reference solution for a problem."""
    pid = uuid.UUID(problem_id)
    with Session(engine) as db:
        ref = db.exec(select(Problem_Reference).where(Problem_Reference.problem_id == pid)).first()
        if not ref:
            raise HTTPException(404, "No reference solution found for this problem")

        db.delete(ref)
        db.commit()

        return {"message": "Reference solution deleted"}


# ═══════════════════════════════════════════════════════
#  PUBLIC: Reference lookup by session (for session history page)
# ═══════════════════════════════════════════════════════

@router.get("/reference/by-session/{session_id}", dependencies=[])
def get_reference_by_session(session_id: str, user_id: str = Depends(get_current_user)):
    """Public endpoint: fetch reference solution for a session's problem. Any authenticated user can access."""
    sid = uuid.UUID(session_id)
    with Session(engine) as db:
        session_row = db.exec(
            select(Interview_Session).where(
                Interview_Session.session_id == sid,
                Interview_Session.user_id == uuid.UUID(user_id),
            )
        ).first()
        if not session_row:
            raise HTTPException(404, "Session not found")

        ref = db.exec(
            select(Problem_Reference).where(Problem_Reference.problem_id == session_row.problem_id)
        ).first()

        if not ref:
            return {"reference": None}

        return {
            "reference": {
                "optimal_approach": ref.optimal_approach,
                "time_complexity": ref.time_complexity,
                "space_complexity": ref.space_complexity,
                "key_insights": ref.key_insights,
                "common_pitfalls": ref.common_pitfalls,
                "pseudocode": ref.pseudocode,
            }
        }

from modules.db import engine
from modules.db import Session_Metrics
from helpers.get_session_data import get_session_row,fetch_session_timer,parse_session_and_user_ids
from sqlmodel import Session
from sqlalchemy import update

def populate_total_time_spent_sec(session_id: str, user_id: str):
    with Session(engine) as db:
        session_uuid, user_uuid = parse_session_and_user_ids(session_id, user_id)
        session_row = get_session_row(db, session_uuid, user_uuid)
        session_timer = fetch_session_timer(db, session_row.session_id)

        total_time_taken = int(
            session_timer["expected_time"] * 60
            - session_timer["remaining_time"]
        )

        stmt = (
            update(Session_Metrics)
            .where(Session_Metrics.session_id == session_row.session_id)
            .values(total_time_spent_sec=total_time_taken)
        )

        db.exec(stmt)
        db.commit()
   
def populate_time_to_first_submission_sec(session_id: str, user_id: str):
    with Session(engine) as db:
        session_uuid, user_uuid = parse_session_and_user_ids(session_id, user_id)
        session_row = get_session_row(db, session_uuid, user_uuid)
        session_timer = fetch_session_timer(db, session_row.session_id)

        time_to_first_submission = int(
            session_timer["expected_time"] * 60
            - session_timer["remaining_time"]
        )

        stmt = (
            update(Session_Metrics)
            .where(Session_Metrics.session_id == session_row.session_id)
            .where(Session_Metrics.time_to_first_submission_sec.is_(None))
            .values(time_to_first_submission_sec=time_to_first_submission)
        )

        db.exec(stmt)
        db.commit()

def increment_total_submissions(session_id: str, user_id: str):
    with Session(engine) as db:
        session_uuid, user_uuid = parse_session_and_user_ids(session_id, user_id)
        session_row = get_session_row(db, session_uuid, user_uuid)

        stmt = (
            update(Session_Metrics)
            .where(Session_Metrics.session_id == session_row.session_id)
            .values(total_submissions=Session_Metrics.total_submissions + 1)
        )

        db.exec(stmt)
        db.commit()

def increment_hints_used(session_id: str, user_id: str):
    with Session(engine) as db:
        session_uuid, user_uuid = parse_session_and_user_ids(session_id, user_id)
        session_row = get_session_row(db, session_uuid, user_uuid)

        stmt = (
            update(Session_Metrics)
            .where(Session_Metrics.session_id == session_row.session_id)
            .values(hints_used=Session_Metrics.hints_used + 1)
        )

        db.exec(stmt)
        db.commit()

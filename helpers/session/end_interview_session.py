# import langgraph agent , use checkpointer with session id to clear the data of the session 
from modules.db import Interview_Session
from sqlmodel import Session,select

def clear_interview_checkpoints(checkpointer, session_id):
    if checkpointer is None:
        return False
    try:
        checkpointer.delete_thread(str(session_id))
        return True
    except Exception as exc:
        print(f"Could not clear checkpoints for session {session_id}: {exc}")
        return False

def set_session_terminated(db: Session, session_id: str) -> bool:
    session_row = db.exec(
        select(Interview_Session)
        .where(Interview_Session.session_id == session_id)
    ).first()

    if not session_row:
        return False

    session_row.status = "TERMINATED"

    db.add(session_row)  # optional if already loaded from db
    db.commit()
    db.refresh(session_row)

    return True
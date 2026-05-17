# import langgraph agent , use checkpointer with session id to clear the data of the session 
from sqlmodel import Session

def clear_interview_checkpoints(checkpointer, session_id):
    if checkpointer is None:
        return False
    try:
        checkpointer.delete_thread(str(session_id))
        return True
    except Exception as exc:
        print(f"Could not clear checkpoints for session {session_id}: {exc}")
        return False

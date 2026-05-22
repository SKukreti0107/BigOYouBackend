import os

from dotenv import load_dotenv

from helpers.session.end_interview_session import clear_interview_checkpoints

load_dotenv()

from .llm import base_llm
from .graph_builder import create_interview_graph

_pg_pool = None
checkpointer = None
graph = None


def init_agent_graph() -> bool:
    global _pg_pool, checkpointer, graph

    if graph is not None:
        return True

    db_url = os.getenv("DB_URL")
    if not db_url:
        print("AI agent init skipped: DB_URL is not configured")
        return False

    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg_pool import ConnectionPool
        from psycopg.rows import dict_row

        _pg_pool = ConnectionPool(
            conninfo=db_url,
            kwargs={"autocommit": True, "row_factory": dict_row},
            min_size=1,
            max_size=10,
            max_lifetime=300.0,
            max_idle=30.0,
            check=ConnectionPool.check_connection,
        )
        checkpointer = PostgresSaver(conn=_pg_pool)
        checkpointer.setup()
        graph = create_interview_graph(checkpointer)
        return True
    except Exception as exc:
        print(f"AI agent init failed: {exc}")
        graph = None
        checkpointer = None
        if _pg_pool is not None:
            try:
                _pg_pool.close()
            except Exception:
                pass
            _pg_pool = None
        return False


def get_graph():
    if graph is None:
        raise RuntimeError("AI agent graph is unavailable")
    return graph


def is_agent_available() -> bool:
    return graph is not None


def clear_agent_checkpoints(session_id: str) -> bool:
    return clear_interview_checkpoints(checkpointer, session_id)


def close_agent_graph() -> None:
    global _pg_pool, checkpointer, graph

    graph = None
    checkpointer = None
    if _pg_pool is not None:
        try:
            _pg_pool.close()
        except Exception:
            pass
    _pg_pool = None

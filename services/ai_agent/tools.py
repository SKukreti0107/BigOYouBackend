# from dataclasses import dataclass
# from langchain.tools import tool, ToolRuntime

# @dataclass
# class Context:
#     """Custom runtime context schema"""

# @tool
# def get_problem_reference(problem_id: str) -> dict:
#     """Fetch internal reference info for a given problem id."""
#     return {}

# @tool
# def get_user_code(session_id: str) -> str:
#     """Fetch the current user code for a given session."""
#     return ""

# @tool
# def store_message(role: str, content: str) -> None:
#     """Store a chat message in session history."""
#     return None

# @tool 
# def get_session_state(session_id: str) -> dict:
#     """Fetch the current interview session state for a given session."""
#     return {}

# @tool
# def store_feedback(structured_json: dict) -> None:
#     """Persist structured feedback for a session."""
#     return None
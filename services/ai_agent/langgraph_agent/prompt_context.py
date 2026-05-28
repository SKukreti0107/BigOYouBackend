import json

from ..schemas import InterviewAgentState
from .prompts import BASE_PROMPT


def build_complete_prompt(state: InterviewAgentState, phase_prompt: str) -> str:
    problem_statement = state.get("problem_statement") or ""
    problem_references = state.get("problem_references") or {}
    user_code = state.get("user_code") or ""

    if isinstance(problem_references, (dict, list)):
        problem_references_str = json.dumps(problem_references, ensure_ascii=True, indent=2)
    else:
        problem_references_str = str(problem_references)

    base_prompt_filled = BASE_PROMPT.format(
        problem_statement=problem_statement,
        problem_references=problem_references_str,
        user_code=user_code,
    )

    return f"{base_prompt_filled}\n\n{phase_prompt}"

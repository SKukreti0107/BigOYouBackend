from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents.structured_output import ToolStrategy
from langchain.agents import create_agent
from .model import llm
from .system_prompt import (
    PROBLEM_DISCUSSION_PROMPT,
    CODING_PROMPT,
    REVIEW_PROMPT,
    FEEDBACK_PROMPT,
)
from typing import List
from langchain.agents.middleware import dynamic_prompt, ModelRequest
from pydantic import BaseModel, Field


# ── Shared context schema ──────────────────────────────────────────────

class Context(BaseModel):
    """Runtime context injected into every agent invocation."""
    problem_statement: str = Field(description="The coding problem statement that the candidate is solving")
    problem_references: dict = Field(description="Reference solution and metadata for the problem including optimal approach, complexity, and hints")
    user_code: str = Field(description="The current code written by the candidate")


# ── Response schemas ────────────────────────────────────────────────────

class ResponseFormat(BaseModel):
    """Response schema for non-feedback phases."""
    response: str = Field(description="The interviewer's response message to the candidate")


class FeedbackItem(BaseModel):
    """Structured feedback evaluation."""
    strengths: List[str] = Field(description="List of specific strengths demonstrated by the candidate during the interview")
    weaknesses: List[str] = Field(description="List of specific areas where the candidate needs improvement")
    complexity_understanding_score: int = Field(description="Score (0-10) evaluating candidate's understanding of time and space complexity")
    communication_score: int = Field(description="Score (0-10) evaluating candidate's ability to explain their thought process clearly")
    problem_solving_score: int = Field(description="Score (0-10) evaluating candidate's problem-solving approach, code quality, and correctness")
    final_verdict: str = Field(description="Concise hiring recommendation and what the candidate should focus on to improve")


class FeedbackResponseFormat(BaseModel):
    """Response schema for the FEEDBACK phase. The feedback field is REQUIRED."""
    response: str = Field(description="A brief conversational farewell or closing summary. Do NOT include scores or evaluation here.")
    feedback: FeedbackItem = Field(description="REQUIRED structured feedback. You MUST populate every field with the candidate's assessment.")


# ── Dynamic prompt middleware (formats context into each phase prompt) ──

def _make_prompt_middleware(prompt_template: str):
    """Create a dynamic_prompt middleware that formats the given template with runtime context."""
    @dynamic_prompt
    def _prompt(request: ModelRequest) -> str:
        ctx = request.runtime.context
        return prompt_template.format(
            problem_statement=ctx.problem_statement,
            problem_references=ctx.problem_references,
            user_code=ctx.user_code,
        )
    return _prompt


# ── Shared checkpointer (conversation history is shared across all agents via thread_id) ──

checkpointer = InMemorySaver()


# ── Per-phase agents ────────────────────────────────────────────────────

discussion_agent = create_agent(
    model=llm,
    system_prompt=PROBLEM_DISCUSSION_PROMPT,
    context_schema=Context,
    middleware=[_make_prompt_middleware(PROBLEM_DISCUSSION_PROMPT)],
    response_format=ToolStrategy(ResponseFormat),
    checkpointer=checkpointer,
)

coding_agent = create_agent(
    model=llm,
    system_prompt=CODING_PROMPT,
    context_schema=Context,
    middleware=[_make_prompt_middleware(CODING_PROMPT)],
    response_format=ToolStrategy(ResponseFormat),
    checkpointer=checkpointer,
)

review_agent = create_agent(
    model=llm,
    system_prompt=REVIEW_PROMPT,
    context_schema=Context,
    middleware=[_make_prompt_middleware(REVIEW_PROMPT)],
    response_format=ToolStrategy(ResponseFormat),
    checkpointer=checkpointer,
)

feedback_agent = create_agent(
    model=llm,
    system_prompt=FEEDBACK_PROMPT,
    context_schema=Context,
    middleware=[_make_prompt_middleware(FEEDBACK_PROMPT)],
    response_format=ToolStrategy(FeedbackResponseFormat),
    checkpointer=checkpointer,
)


# ── Phase → agent mapping ──────────────────────────────────────────────

phase_agents = {
    "PROBLEM_DISCUSSION": discussion_agent,
    "CODING": coding_agent,
    "REVIEW": review_agent,
    "FEEDBACK": feedback_agent,
}



from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents.structured_output import ToolStrategy
from langchain.agents import create_agent
from .model import llm
from .schemas import (
    ComplexityMetric,
    ComplexityScore,
    FeedbackItem,
    FeedbackResponseFormat,
    KeyMetrics,
    ScoreWithNotes,
    Scores,
    SessionSummary,
    StrengthItem,
    Verdict,
    WeaknessItem,
)
from .system_prompt import (
    PROBLEM_DISCUSSION_PROMPT,
    CODING_PROMPT,
    REVIEW_PROMPT,
    FEEDBACK_PROMPT,
)
from langchain.agents.middleware import dynamic_prompt, ModelRequest
from pydantic import BaseModel, Field


# ── Shared context schema (non-feedback phases) ───────────────────────

class Context(BaseModel):
    """Runtime context injected into non-feedback agent invocations."""
    problem_statement: str = Field(description="The coding problem statement that the candidate is solving")
    problem_references: dict = Field(description="Reference solution and metadata for the problem including optimal approach, complexity, and hints")
    user_code: str = Field(description="The current code written by the candidate")


# ── Feedback-phase context (includes session metrics) ─────────────────

class FeedbackContext(BaseModel):
    """Extended context for the feedback agent — includes session metrics for comprehensive evaluation."""
    problem_statement: str = Field(description="The coding problem statement that the candidate is solving")
    problem_references: dict = Field(description="Reference solution and metadata for the problem")
    user_code: str = Field(description="The final code written by the candidate")
    difficulty: str = Field(description="Problem difficulty level: Easy, Medium, or Hard")
    expected_time_minutes: int = Field(description="Expected time to solve the problem in minutes")
    total_time_spent_sec: int = Field(description="Actual time the candidate spent in seconds")
    total_submissions: int = Field(description="Number of code submissions the candidate made")
    hints_used: int = Field(description="Number of hints the candidate requested")


# ── Response schemas ────────────────────────────────────────────────────

class ResponseFormat(BaseModel):
    """Response schema for non-feedback phases."""
    response: str = Field(description="The interviewer's response message to the candidate")


# ── Dynamic prompt middleware ──────────────────────────────────────────

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


def _make_feedback_prompt_middleware(prompt_template: str):
    """Create a dynamic_prompt middleware for the feedback agent — formats extra metric fields."""
    @dynamic_prompt
    def _prompt(request: ModelRequest) -> str:
        ctx = request.runtime.context
        return prompt_template.format(
            problem_statement=ctx.problem_statement,
            problem_references=ctx.problem_references,
            user_code=ctx.user_code,
            difficulty=ctx.difficulty,
            expected_time_minutes=ctx.expected_time_minutes,
            total_time_spent_sec=ctx.total_time_spent_sec,
            total_submissions=ctx.total_submissions,
            hints_used=ctx.hints_used,
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
    context_schema=FeedbackContext,
    middleware=[_make_feedback_prompt_middleware(FEEDBACK_PROMPT)],
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



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
from typing import List, Literal
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


# ── Comprehensive feedback models (mirrors feedback.json) ─────────────

class ScoreWithNotes(BaseModel):
    """A score accompanied by evaluator notes."""
    score: int = Field(description="Integer score from 0 to 10 where 0 = no demonstration and 10 = exceptional")
    notes: str = Field(description="Brief evaluator notes justifying this score")


class ComplexityScore(BaseModel):
    """Complexity analysis score with identified complexities."""
    score: int = Field(description="Integer score from 0 to 10 evaluating understanding of time/space complexity")
    time_complexity: str = Field(description="The time complexity of the candidate's solution, e.g. O(n), O(n log n)")
    space_complexity: str = Field(description="The space complexity of the candidate's solution, e.g. O(1), O(n)")
    notes: str = Field(description="Notes on the candidate's complexity analysis and understanding")


class Scores(BaseModel):
    """All evaluation scores."""
    problem_solving: ScoreWithNotes = Field(description="Evaluation of the candidate's problem-solving approach, code quality, and correctness")
    complexity_analysis: ComplexityScore = Field(description="Evaluation of the candidate's understanding and analysis of time and space complexity")
    communication: ScoreWithNotes = Field(description="Evaluation of the candidate's ability to explain their thought process and approach clearly")


class StrengthItem(BaseModel):
    """A specific strength demonstrated by the candidate."""
    category: str = Field(description="Category of the strength, e.g. 'Data Structures', 'Algorithm Design', 'Communication', 'Edge Cases'")
    title: str = Field(description="Short title for the strength, e.g. 'Correct LRU Design'")
    description: str = Field(description="Detailed description of the strength demonstrated")
    impact: Literal["high", "medium", "low"] = Field(description="Impact level of this strength on the overall evaluation")


class WeaknessItem(BaseModel):
    """A specific area where the candidate needs improvement."""
    category: str = Field(description="Category of the weakness, e.g. 'Optimization', 'Communication', 'Edge Cases', 'Complexity'")
    title: str = Field(description="Short title for the weakness, e.g. 'Space Overhead'")
    description: str = Field(description="Detailed description of the area for improvement")
    severity: Literal["high", "medium", "low"] = Field(description="Severity level of this weakness")


class ComplexityMetric(BaseModel):
    """Runtime or memory complexity assessment."""
    value: str = Field(description="The complexity value, e.g. 'O(n)', 'O(1)', 'O(n log n)'")
    status: Literal["optimal", "acceptable", "suboptimal"] = Field(description="Whether this complexity is optimal, acceptable, or suboptimal for the problem")


class KeyMetrics(BaseModel):
    """Key performance metrics for the candidate's solution."""
    runtime_complexity: ComplexityMetric = Field(description="Assessment of the solution's time complexity")
    memory_efficiency: ComplexityMetric = Field(description="Assessment of the solution's space complexity")
    coding_speed_percentile: int = Field(description="Percentile (0-100) of coding speed. Compute as: max(0, min(100, 100 - int((total_time_spent_sec / (expected_time_minutes * 60)) * 100))). Higher = faster.")


class Verdict(BaseModel):
    """Final hiring verdict."""
    decision: str = Field(description="Hiring decision: 'Strong Hire', 'Hire', 'Lean Hire', 'Lean No Hire', 'No Hire', or 'Strong No Hire'")
    confidence: float = Field(description="Confidence in the decision as a float from 0.0 to 1.0")
    summary: str = Field(description="One or two sentence summary of the verdict and what the candidate should focus on")


class SessionSummary(BaseModel):
    """High-level summary of the interview session."""
    overall_score: int = Field(description="Overall score from 0 to 100 derived as a weighted average: problem_solving (40%) + complexity_analysis (30%) + communication (30%), each scaled from 0-10 to 0-100")
    performance_label: str = Field(description="One of: 'Exceptional', 'Strong Performance', 'Adequate', 'Below Expectations', 'Poor'")
    difficulty: str = Field(description="Problem difficulty: 'Easy', 'Medium', or 'Hard'")
    time_spent_seconds: int = Field(description="Total time the candidate spent in seconds (use the provided session metric)")


class FeedbackItem(BaseModel):
    """Comprehensive structured feedback — matches the full feedback report format."""
    session_summary: SessionSummary = Field(description="High-level session summary with overall score")
    scores: Scores = Field(description="Detailed scores with notes for problem solving, complexity analysis, and communication")
    strengths: List[StrengthItem] = Field(description="List of specific strengths with category, title, description, and impact. If none, use a single item with category='General', title='None Demonstrated', description='No strengths observed', impact='low'")
    weaknesses: List[WeaknessItem] = Field(description="List of specific weaknesses with category, title, description, and severity")
    key_metrics: KeyMetrics = Field(description="Key metrics including runtime/memory complexity assessment and coding speed percentile")
    final_verdict: Verdict = Field(description="Final hiring decision with confidence score and summary")


class FeedbackResponseFormat(BaseModel):
    """Response schema for the FEEDBACK phase. The feedback field is REQUIRED."""
    response: str = Field(description="A brief conversational farewell or closing summary. Do NOT include scores or evaluation here.")
    feedback: FeedbackItem = Field(description="REQUIRED comprehensive feedback report. You MUST populate every nested field.")


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



from pydantic import BaseModel,Field
from typing import Literal,Annotated,Sequence,Optional,Dict,Any,TypedDict,List
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

#-------------------------------------------------------------------------------------------------------
#### Agent internal phase assesment schemas
class CriterionAssessment(BaseModel):
    completed:bool = Field(description="Weather this criterion is satisfied")
    confidence:float = Field(ge=0.0, le=1.0, description="Confidence for this criterion")
    reason:str = Field(description="Short evidence backed rationale")

class DiscussionAssessment(BaseModel):
    approach_explained: CriterionAssessment
    edge_cases_discussed: CriterionAssessment
    complexity_discussed: CriterionAssessment
    next_question: str = Field(min_length=1, description="Interviewer follow-up question for the candidate")
    

class CodingAssessment(BaseModel):
    code_submitted: CriterionAssessment
    walkthrough_provided: CriterionAssessment
    correctness_discussed: CriterionAssessment
    next_question: str = Field(min_length=1, description="Interviewer follow-up question for coding phase")


class ReviewAssessment(BaseModel):
    optimization_discussed: CriterionAssessment
    edge_case_validation: CriterionAssessment
    final_complexity_summary: CriterionAssessment
    next_question: str = Field(min_length=1, description="Interviewer follow-up question for review phase")

#-------------------------------------------------------------------------------------------------------
##### Agent State Schema 
class InterviewAgentState(TypedDict):
    session_id: str
    phase: Literal["PROBLEM_DISCUSSION", "CODING", "REVIEW", "FEEDBACK"]
    messages: Annotated[Sequence[BaseMessage], add_messages]
    problem_statement: str
    problem_references: Optional[Dict[str, Any]]

    user_code: Optional[str]
    user_code_output: Optional[Dict[str, Any]]
    execution_attempts: int

    discussion_turns: int
    review_turns: int
    coding_turns: int

    total_time_spent_sec: Optional[int]
    total_submissions: Optional[int]
    hints_used: Optional[int]

    time_expired: Optional[bool]
    extra_time_used: Optional[bool]
    extension_count: Optional[int]
    session_ended_by: Optional[str]

    discussion_assessment: Optional[Dict[str, Any]]
    coding_assessment: Optional[Dict[str, Any]]
    review_assessment: Optional[Dict[str, Any]]
    feedback: Optional[Dict[str, Any]]

#-------------------------------------------------------------------------------------------------------
#### Agent Feedback output Schema


class ScoreWithNotes(BaseModel):
    """A score accompanied by evaluator notes."""
    score: int = Field(ge=0, le=10, description="Integer score from 0 to 10")
    notes: str = Field(min_length=1, description="Brief evaluator notes justifying this score")


class ComplexityScore(BaseModel):
    """Complexity analysis score with identified complexities."""
    score: int = Field(ge=0, le=10, description="Integer score from 0 to 10 evaluating complexity understanding")
    time_complexity: str = Field(min_length=1, description="The time complexity, e.g. O(n), O(n log n)")
    space_complexity: str = Field(min_length=1, description="The space complexity, e.g. O(1), O(n)")
    notes: str = Field(min_length=1, description="Notes on complexity analysis")


class Scores(BaseModel):
    """All evaluation scores."""
    problem_solving: ScoreWithNotes
    complexity_analysis: ComplexityScore
    communication: ScoreWithNotes


class StrengthItem(BaseModel):
    """A specific strength demonstrated by the candidate."""
    category: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    impact: Literal["high", "medium", "low"]


class WeaknessItem(BaseModel):
    """A specific area where the candidate needs improvement."""
    category: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    severity: Literal["high", "medium", "low"]


class ComplexityMetric(BaseModel):
    """Runtime or memory complexity assessment."""
    value: str = Field(min_length=1)
    status: Literal["optimal", "acceptable", "suboptimal"]


class KeyMetrics(BaseModel):
    """Key performance metrics for the candidate's solution."""
    runtime_complexity: ComplexityMetric
    memory_efficiency: ComplexityMetric
    coding_speed_percentile: int = Field(ge=0, le=100)


class Verdict(BaseModel):
    """Final hiring verdict."""
    decision: Literal["Strong Hire", "Hire", "Lean Hire", "Lean No Hire", "No Hire", "Strong No Hire"]
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=1)


class SessionSummary(BaseModel):
    """High-level summary of the interview session."""
    overall_score: int = Field(ge=0, le=100)
    performance_label: Literal["Exceptional", "Strong Performance", "Adequate", "Below Expectations", "Poor"]
    difficulty: Literal["Easy", "Medium", "Hard"]
    time_spent_seconds: int = Field(ge=0)


class FeedbackItem(BaseModel):
    """Comprehensive structured feedback."""
    session_summary: SessionSummary
    scores: Scores
    strengths: List[StrengthItem]
    weaknesses: List[WeaknessItem]
    key_metrics: KeyMetrics
    final_verdict: Verdict


class FeedbackResponseFormat(BaseModel):
    """Response schema for FEEDBACK phase."""
    response: str = Field(min_length=1, description="Brief conversational closing summary.")
    feedback: FeedbackItem
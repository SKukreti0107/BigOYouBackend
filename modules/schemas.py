from pydantic import BaseModel
from typing import Literal


class LoginOrSignUpRequest(BaseModel):
    email: str
    password: str


class SignUpRequest(BaseModel):
    email: str
    password: str
    username: str | None = None


class ProfileUpdateRequest(BaseModel):
    email: str
    username: str | None = None


class PasswordUpdateRequest(BaseModel):
    current_password: str
    new_password: str


class ExecuteRequest(BaseModel):
    language: str
    code: str
    session_id: str


class PhaseRequest(BaseModel):
    session_id: str
    message: str
    code: str | None = None
    language: str | None = None
    role: Literal["user", "system"] = "user"
    time_expired: bool | None = None
    extra_time_used: bool | None = None
    extension_count: int | None = None
    session_ended_by: str | None = None
    exit_clicked: bool | None = None


class AgentInitRequest(BaseModel):
    session_id: str
    message: str | None = "[SYSTEM EVENT] Start the interview"
    role: Literal["user", "system"] = "system"


class TimeoutActionRequest(BaseModel):
    session_id: str
    action: Literal["REVIEW", "END_FEEDBACK", "EXTEND"]
    extension_minutes: int = 15


# ── Admin Schemas ──

class ProblemCreateRequest(BaseModel):
    title: str
    statement: str
    example: str
    difficulty: Literal["Easy", "Medium", "Hard"]
    expected_time: int
    topics: list[str] = []

    # Optional reference solution fields
    optimal_approach: str | None = None
    time_complexity: str | None = None
    space_complexity: str | None = None
    key_insights: str | None = None
    common_pitfalls: str | None = None
    pseudocode: str | None = None
    leetcode_slug: str | None = None
    leetcode_url: str | None = None


class ProblemUpdateRequest(BaseModel):
    title: str | None = None
    statement: str | None = None
    example: str | None = None
    difficulty: Literal["Easy", "Medium", "Hard"] | None = None
    expected_time: int | None = None
    topics: list[str] | None = None


class ReferenceCreateRequest(BaseModel):
    optimal_approach: str
    time_complexity: str
    space_complexity: str
    key_insights: str
    common_pitfalls: str | None = None
    pseudocode: str | None = None


class ReferenceUpdateRequest(BaseModel):
    optimal_approach: str | None = None
    time_complexity: str | None = None
    space_complexity: str | None = None
    key_insights: str | None = None
    common_pitfalls: str | None = None
    pseudocode: str | None = None

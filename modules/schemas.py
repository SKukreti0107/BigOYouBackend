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

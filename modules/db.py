# import psycopg2
from dotenv import load_dotenv
import os
load_dotenv()
from sqlmodel import SQLModel,create_engine,Field
import uuid
from enum import Enum
from datetime import datetime
from typing import Optional

conn_string = os.getenv('DB_URL')

#User Table
class Users(SQLModel,table=True):
    user_id: uuid.UUID | None = Field(default=None,primary_key=True)
    email: str 
    pass_hash:str

class DifficultyLevel(str,Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"

class InterviewPhase(str, Enum):
    PROBLEM_DISCUSSION = "PROBLEM_DISCUSSION"
    CODING = "CODING"
    REVIEW = "REVIEW"
    FEEDBACK = "FEEDBACK"

class Problems(SQLModel,table=True):
    problem_id:uuid.UUID | None = Field(default_factory=uuid.uuid4,primary_key=True)
    title:str = Field(index=True, unique=True)
    statement:str
    example:str
    difficulty:DifficultyLevel
    expected_time:int

class User_Problem_Status(SQLModel,table=True):
    user_id: uuid.UUID = Field(
        foreign_key="users.user_id",
        primary_key=True
    )
    problem_id: uuid.UUID = Field(
        foreign_key="problems.problem_id",
        primary_key=True
    )
    is_completed: bool = Field(default=False, nullable=False)
    solved_at: Optional[datetime] = None


class Problem_topics(SQLModel,table=True):
    id: int | None = Field(default=None, primary_key=True)
    problem_id: uuid.UUID = Field(foreign_key="problems.problem_id")
    topic: str = Field(index=True)

class Interview_Session(SQLModel, table=True):
    session_id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.user_id",index=True)
    problem_id: uuid.UUID = Field(foreign_key="problems.problem_id")
    topic: str = Field(index=True)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="ACTIVE", index=True)
    phase: InterviewPhase = Field(default=InterviewPhase.PROBLEM_DISCUSSION)

class Session_Code_State(SQLModel, table=True):
    snapshot_id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="interview_session.session_id", index=True)
    code: str
    language: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    

class Session_Message(SQLModel, table=True):
    message_id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="interview_session.session_id", index=True)
    role: str
    content: str
    phase: InterviewPhase
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Session_Metrics(SQLModel, table=True):
    session_id: uuid.UUID = Field(
        foreign_key="interview_session.session_id",
        primary_key=True
    )
    total_time_spent_sec: int
    time_to_first_submission_sec: int | None
    total_submissions: int
    hints_used: int = 0
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Session_Feedback(SQLModel, table=True):
    session_id: uuid.UUID = Field(
        foreign_key="interview_session.session_id",
        primary_key=True
    )
    strengths: str
    weaknesses: str
    complexity_understanding_score: int
    communication_score: int
    problem_solving_score: int
    final_verdict: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Problem_Reference(SQLModel, table=True):
    ref_id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    problem_id: uuid.UUID = Field(foreign_key="problems.problem_id", unique=True)

    optimal_approach: str
    time_complexity: str
    space_complexity: str
    key_insights: str
    common_pitfalls: str | None = None
    pseudocode: str | None = None


engine = create_engine(
    conn_string,
    echo=True,
    pool_pre_ping=True,
    pool_recycle=3600
    )

def create_db_and_table():
    SQLModel.metadata.create_all(engine)




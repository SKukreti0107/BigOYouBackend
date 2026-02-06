from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents.structured_output import ToolStrategy
from langchain.agents import create_agent
from dataclasses import dataclass
from .model import llm
from .system_prompt import SYSTEM_PROMPT
from typing import List,Optional
from langchain.agents.middleware import dynamic_prompt, ModelRequest


@dataclass
class Context:
    """Custom runtime context schema."""
    session_phase:str
    problem_statement:str
    problem_references:dict
    user_code:str

@dataclass
class ResponseFormat:
    """Response schema for the agent."""
    response: str
    feedback: Optional[List[str]] = None

@dynamic_prompt
def interviewer_prompt(request: ModelRequest) -> str:
    # Access the static context passed during .invoke()
    ctx = request.runtime.context
    
    # Manually format the template with context values
    return SYSTEM_PROMPT.format(
        problem_statement=ctx.problem_statement,
        problem_references=ctx.problem_references,
        session_phase=ctx.session_phase,
        user_code=ctx.user_code
    )

checkpointer = InMemorySaver()



agent = create_agent(
    model=llm,
    system_prompt=SYSTEM_PROMPT,
    context_schema=Context,
    middleware=[interviewer_prompt],
    response_format=ToolStrategy(ResponseFormat),
    checkpointer=checkpointer
)



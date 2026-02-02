from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents.structured_output import ToolStrategy
from langchain.agents import create_agent
from dataclasses import dataclass
from .model import llm
from .system_prompt import SYSTEM_PROMPT
# from .tools import get_problem_context,get_problem_reference,get_session_state,get_user_code
from typing import List,Optional

DummyProblemReference = {
    
    "title": "Two Sum",
    "optimal_approach": "Use a hash map to store seen values and their indices; for each number, check if target - num exists.",
    "time_complexity": "O(n)",
    "space_complexity": "O(n)",
    "key_insights": "A single pass with complement lookup avoids nested loops.",
    "common_pitfalls": "Using the same element twice; forgetting to store index after check.",
    "pseudocode": "map = {}\nfor i, x in nums:\n  if target-x in map: return [map[target-x], i]\n  map[x] = i"
    
}

DummyContext = {
    "session_phase":"PROBLEM_UNDERSTANDING",
    "problem_statement":"Given an array of integers nums and an integer target, return the indices of the two numbers that add up to target. You may assume each input has exactly one solution, and you cannot use the same element twice.",
    "problem_references":DummyProblemReference,
    "user_code":""
}


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
    

checkpointer = InMemorySaver()

agent = create_agent(
    model=llm,
    system_prompt=SYSTEM_PROMPT,
    # tools=[get_problem_context,get_problem_reference,get_session_state,get_user_code],
    context_schema=Context,
    response_format=ToolStrategy(ResponseFormat),
    checkpointer=checkpointer
)

config = {"configurable": {"thread_id": "1"}}

# response = agent.invoke(
#     {"messages": [{"role": "user", "content": "Hi"}]},
#     config=config,
#     context=Context(session_phase=DummyContext['session_phase'],problem_statement=DummyContext["problem_statement"],problem_references=DummyContext["problem_references"],user_code=DummyContext["user_code"])
# )

# print(response['structured_response'])
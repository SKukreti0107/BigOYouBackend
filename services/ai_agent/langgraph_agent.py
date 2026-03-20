from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver


from .schemas import *
from .system_prompt import *
from .helpers.prompt_builder import *
from .helpers.internal_phase_assessment import _merge_criterion,_is_complete


#for dev in mem later persistent db
checkpointer = MemorySaver()
load_dotenv()

base_llm = ChatGoogleGenerativeAI(
    model = "gemini-flash-lite-latest", # for testing 
    # model = "gemini-3.1-flash-lite-preview" # for prod
)

#---------------------------------------------------------------------------------------
#graph nodes

def interview_init_node(state: InterviewAgentState) -> dict:
    existing_messages = list(state.get("messages", []))
    # Skip only if this session has already produced interviewer output.
    if any(isinstance(msg, AIMessage) for msg in existing_messages):
        return {"phase": "PROBLEM_DISCUSSION"}

    final_prompt = build_complete_prompt(state, INTERVIEW_INIT_PROMPT)

    starter_content = "Please start the interview."
    if existing_messages and isinstance(existing_messages[-1], HumanMessage):
        starter_content = str(existing_messages[-1].content or "").strip() or starter_content

    messages = [
        SystemMessage(content=final_prompt),
        HumanMessage(content=starter_content),
    ]

    res = base_llm.invoke(messages)

    print(f"AI message: {res.content}")

    return {
        "phase": "PROBLEM_DISCUSSION",
        "messages": [res]
    }


def problem_discussion_phase_node(state: InterviewAgentState) -> dict:

    final_prompt = build_complete_prompt(state,PROBLEM_DISCUSSION_PROMPT)

    messages = state.get("messages", [])

    if not messages or not isinstance(messages[-1], HumanMessage):
        return {}

    # LLM call with structured output
    res: DiscussionAssessment = base_llm.with_structured_output(
        DiscussionAssessment
    ).invoke([
        SystemMessage(content=final_prompt),
        *messages[-6:],  # windowing (important)
    ])

    previous_assessment = state.get("discussion_assessment") or {}

    updated_assessment = {
        "approach_explained": _merge_criterion(
            previous_assessment.get("approach_explained"),
            res.approach_explained,
        ),
        "edge_cases_discussed": _merge_criterion(
            previous_assessment.get("edge_cases_discussed"),
            res.edge_cases_discussed,
        ),
        "complexity_discussed": _merge_criterion(
            previous_assessment.get("complexity_discussed"),
            res.complexity_discussed,
        ),
    }

    assistant_message = AIMessage(content=res.next_question)

    return {
        "phase": "PROBLEM_DISCUSSION",
        "messages": [assistant_message],
        "discussion_turns": state.get("discussion_turns", 0) + 1,
        "discussion_assessment": updated_assessment,
    }

def discussion_router(state: InterviewAgentState):
    discussion_phase_flags = state.get("discussion_assessment") or {}
    if not isinstance(discussion_phase_flags, dict):
        return "PROBLEM_DISCUSSION"

    approach_flags = discussion_phase_flags.get("approach_explained") or {}
    edge_case_flags = discussion_phase_flags.get("edge_cases_discussed") or {}
    complexity_flags = discussion_phase_flags.get("complexity_discussed") or {}

    if (
        _is_complete(approach_flags) and
        _is_complete(edge_case_flags) and
        _is_complete(complexity_flags)
    ):
        return "CODING"

    return "PROBLEM_DISCUSSION"


def coding_phase_node(state: InterviewAgentState) -> dict:
    final_prompt = build_complete_prompt(state,CODING_PROMPT)
    messages = state.get("messages", [])

    if not messages or not isinstance(messages[-1], HumanMessage):
        return {}

    res: CodingAssessment = base_llm.with_structured_output(
        CodingAssessment
    ).invoke([
        SystemMessage(content=final_prompt),
        *messages[-6:],   # windowing
    ])

    previous_assessment = state.get("coding_assessment") or {}
    updated_assessment = {
        "code_submitted": _merge_criterion(
            previous_assessment.get("code_submitted"),
            res.code_submitted,
        ),
        "walkthrough_provided": _merge_criterion(
            previous_assessment.get("walkthrough_provided"),
            res.walkthrough_provided,
        ),
        "correctness_discussed": _merge_criterion(
            previous_assessment.get("correctness_discussed"),
            res.correctness_discussed,
        ),
    }
    assistant_message = AIMessage(content=res.next_question)

    return {
        "phase": "CODING",
        "messages": [assistant_message],
        "coding_turns": state.get("coding_turns", 0) + 1,
        "coding_assessment": updated_assessment,
    }


def coding_router(state: InterviewAgentState):
    coding_phase_flags = state.get("coding_assessment") or {}
    if not isinstance(coding_phase_flags, dict):
        return "CODING"

    code_submitted_flags = coding_phase_flags.get("code_submitted") or {}
    walkthrough_flags = coding_phase_flags.get("walkthrough_provided") or {}
    correctness_flags = coding_phase_flags.get("correctness_discussed") or {}

    if (
        _is_complete(code_submitted_flags) and
        _is_complete(walkthrough_flags) and
        _is_complete(correctness_flags)
    ):
        return "REVIEW"

    return "CODING"

def review_phase_node(state: InterviewAgentState) -> dict:
    final_prompt = build_complete_prompt(state,REVIEW_PROMPT)
    messages = state.get("messages", [])

    if not messages or not isinstance(messages[-1], HumanMessage):
        return {}

    res: ReviewAssessment = base_llm.with_structured_output(
        ReviewAssessment
    ).invoke([
        SystemMessage(content=final_prompt),
        *messages[-6:],   # windowing
    ])

    previous_assessment = state.get("review_assessment") or {}
    updated_assessment = {
        "optimization_discussed": _merge_criterion(
            previous_assessment.get("optimization_discussed"),
            res.optimization_discussed,
        ),
        "edge_case_validation": _merge_criterion(
            previous_assessment.get("edge_case_validation"),
            res.edge_case_validation,
        ),
        "final_complexity_summary": _merge_criterion(
            previous_assessment.get("final_complexity_summary"),
            res.final_complexity_summary,
        ),
    }
    assistant_message = AIMessage(content=res.next_question)

    return {
        "phase": "REVIEW",
        "messages": [assistant_message],
        "review_turns": state.get("review_turns", 0) + 1,
        "review_assessment": updated_assessment,
    }

def review_router(state: InterviewAgentState):
    review_phase_flags = state.get("review_assessment") or {}
    if not isinstance(review_phase_flags, dict):
        return "REVIEW"

    optimization_flags = review_phase_flags.get("optimization_discussed") or {}
    edge_case_validation_flags = review_phase_flags.get("edge_case_validation") or {}
    final_complexity_flags = review_phase_flags.get("final_complexity_summary") or {}

    if (
        _is_complete(optimization_flags) and
        _is_complete(edge_case_validation_flags) and
        _is_complete(final_complexity_flags)
    ):
        return "FEEDBACK"

    return "REVIEW"

def feedback_phase_node(state: InterviewAgentState) -> dict:
    final_prompt = build_complete_prompt(state,FEEDBACK_PROMPT)
    messages = state.get("messages", [])
    if not messages:
        return {}

    discussion_assessment = state.get("discussion_assessment") or {}
    coding_assessment = state.get("coding_assessment") or {}
    review_assessment = state.get("review_assessment") or {}
    
    total_time = state.get("total_time_spent_sec") or 0
    total_submissions = state.get("total_submissions") or 0
    hints_used = state.get("hints_used") or 0

    context_message = HumanMessage(
        content=
        f"**Internal Assessment State:**\n"
        f"Discussion Assessment: {discussion_assessment}\n"
        f"Coding Assessment: {coding_assessment}\n"
        f"Review Assessment: {review_assessment}\n\n"
        f"**Session Metrics:**\n"
        f"Time spent (seconds): {total_time}\n"
        f"Total Submissions Evaluated: {total_submissions}\n"
        f"Hints used: {hints_used}\n"
    )

    res = base_llm.with_structured_output(
        FeedbackResponseFormat
    ).invoke([
        SystemMessage(content=final_prompt),
        *messages[-6:],
        context_message,
    ])

    assistant_message = AIMessage(content=res.response)

    return {
        "messages": [assistant_message],
        "phase": "FEEDBACK",
        "feedback": res.feedback.model_dump(),
    }

#-------------------------------------------------------
#compiling the graph:

def create_interview_graph(checkpointer_obj: MemorySaver):
    workflow = StateGraph(InterviewAgentState)

    workflow.add_node("interview_init_node", interview_init_node)
    workflow.add_node("problem_discussion_phase_node", problem_discussion_phase_node)
    workflow.add_node("coding_phase_node", coding_phase_node)
    workflow.add_node("review_phase_node", review_phase_node)
    workflow.add_node("feedback_phase_node", feedback_phase_node)

    workflow.set_entry_point("interview_init_node")
    workflow.add_edge("interview_init_node", "problem_discussion_phase_node")
    workflow.add_edge("feedback_phase_node", END)

    workflow.add_conditional_edges(
        source="problem_discussion_phase_node",
        path=discussion_router,
        path_map={
            "CODING": "coding_phase_node",
            "PROBLEM_DISCUSSION": "problem_discussion_phase_node",
        },
    )

    workflow.add_conditional_edges(
        source="coding_phase_node",
        path=coding_router,
        path_map={
            "REVIEW": "review_phase_node",
            "CODING": "coding_phase_node",
        },
    )

    workflow.add_conditional_edges(
        source="review_phase_node",
        path=review_router,
        path_map={
            "REVIEW": "review_phase_node",
            "FEEDBACK": "feedback_phase_node"
        },
    )

    return workflow.compile(
        checkpointer=checkpointer_obj,
        interrupt_after=[
            "problem_discussion_phase_node",
            "coding_phase_node",
            "review_phase_node",
            "feedback_phase_node",
        ],
    )


graph = create_interview_graph(checkpointer)
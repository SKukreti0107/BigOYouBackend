from langgraph.graph import END, StateGraph

from ..schemas import InterviewAgentState
from .graph_nodes import (
    coding_phase_node,
    coding_router,
    discussion_router,
    feedback_phase_node,
    interview_init_node,
    problem_discussion_phase_node,
    review_phase_node,
    review_router,
)


def create_interview_graph(checkpointer_obj):
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
            "FEEDBACK": "feedback_phase_node",
            "END": END,
        },
    )

    workflow.add_conditional_edges(
        source="coding_phase_node",
        path=coding_router,
        path_map={
            "REVIEW": "review_phase_node",
            "CODING": "coding_phase_node",
            "FEEDBACK": "feedback_phase_node",
            "END": END,
        },
    )

    workflow.add_conditional_edges(
        source="review_phase_node",
        path=review_router,
        path_map={
            "REVIEW": "review_phase_node",
            "FEEDBACK": "feedback_phase_node",
            "END": END,
        },
    )

    return workflow.compile(
        checkpointer=checkpointer_obj,
        interrupt_after=[
            "problem_discussion_phase_node",
            "coding_phase_node",
            "review_phase_node",
        ],
    )

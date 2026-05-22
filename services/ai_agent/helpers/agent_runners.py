from langchain_core.messages import HumanMessage

from .message_normalizer import normalize_message_text


def get_last_ai_message(state):
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if str(getattr(msg, "type", "")).lower() == "ai":
            return normalize_message_text(getattr(msg, "content", ""))
    return ""


def run_interview_turn(graph, thread_id, user_input, state=None, is_first=False):

    config = {
        "configurable": {
            "thread_id": thread_id
        },
        "recursion_limit": 1000
    }

    if is_first:
        result = graph.invoke(state, config=config)
    else:
        # 1. Provide the new message to state memory without overriding the timeline
        graph.update_state(config, {"messages": [HumanMessage(content=user_input)]})
        # 2. Invoke with `None` to tell LangGraph to resume from suspended edge
        result = graph.invoke(None, config=config)

    # If the graph transitioned to FEEDBACK phase but didn't generate feedback yet
    # (because it was interrupted after review_phase_node), invoke it once more to run feedback_phase_node
    if result.get("phase") == "FEEDBACK" and not result.get("feedback"):
        print("Graph transitioned to FEEDBACK but feedback is missing. Resuming to execute feedback_phase_node...")
        result = graph.invoke(None, config=config)
    
    # new return format  
    return {
        "response": get_last_ai_message(result),
        "feedback": result.get("feedback") if result.get("phase") == "FEEDBACK" else None,
        "phase": result.get("phase")
    }


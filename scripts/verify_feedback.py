import sys
import os
import uuid

# Adjust python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select
from modules.db import engine, Session_Feedback
from services.ai_agent.langgraph_agent.core import init_agent_graph, get_graph
from services.ai_agent.langgraph_agent.graph_nodes import feedback_phase_node

def verify():
    # Init agent graph
    init_agent_graph()

    thread_id = "234fc109-74ee-4910-9412-13757fd8558e"
    config = {"configurable": {"thread_id": thread_id}}

    snapshot = get_graph().get_state(config)
    state = snapshot.values if snapshot else {}

    if not state:
        print("Could not retrieve state snapshot for thread:", thread_id)
        return

    print("Loaded state keys:", list(state.keys()))
    print("Pre-existing test_case_results in state:", state.get("test_case_results"))
    
    # Simulate missing test cases
    state["test_case_results"] = []

    print("Running feedback_phase_node manually...")
    res = feedback_phase_node(state)

    print("Result keys:", list(res.keys()))
    print("Result feedback contains test_cases:", "test_cases" in res.get("feedback", {}))
    if "feedback" in res and "test_cases" in res["feedback"]:
        tc_res = res["feedback"]["test_cases"]
        print(f"Number of evaluated test cases: {len(tc_res)}")
        if tc_res:
            print("First test case result:", tc_res[0])
    
    print("Returned test_case_results list length:", len(res.get("test_case_results", [])))

    if "feedback" in res and res["feedback"].get("test_cases"):
        with Session(engine) as db:
            existing_fb = db.exec(
                select(Session_Feedback)
                .where(Session_Feedback.session_id == uuid.UUID(thread_id))
            ).first()
            if existing_fb:
                existing_fb.feedback_json = res["feedback"]
                db.add(existing_fb)
                db.commit()
                print("SUCCESS: Successfully saved evaluated test cases to Session_Feedback database!")
            else:
                print("WARNING: Could not find pre-existing Session_Feedback row to update.")

if __name__ == "__main__":
    verify()

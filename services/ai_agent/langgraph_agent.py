from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
import os

from helpers.session.end_interview_session import clear_interview_checkpoints

from .schemas import *
from .system_prompt import *
from .helpers.prompt_builder import *
from .helpers.internal_phase_assessment import _merge_criterion,_is_complete


load_dotenv()

_pg_pool = None
checkpointer = None
graph = None

base_llm = ChatGoogleGenerativeAI(
    # model = "gemini-flash-lite-latest", # for testing 
    model = "gemini-3.1-flash-lite" # for prod
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

    approach_flags = updated_assessment.get("approach_explained") or {}
    edge_case_flags = updated_assessment.get("edge_cases_discussed") or {}
    complexity_flags = updated_assessment.get("complexity_discussed") or {}

    new_turns = state.get("discussion_turns", 0) + 1

    is_complete_discussion = (
        _is_complete(approach_flags) and
        _is_complete(edge_case_flags) and
        _is_complete(complexity_flags) and
        new_turns >= 2
    )

    phase = "CODING" if is_complete_discussion else "PROBLEM_DISCUSSION"

    assistant_message = AIMessage(content=res.next_question)

    return {
        "phase": phase,
        "messages": [assistant_message],
        "discussion_turns": new_turns,
        "discussion_assessment": updated_assessment,
    }

def discussion_router(state: InterviewAgentState):

    if state.get("exit_clicked"):
        return "END"

    # Shortcut: if the session was ended by timeout, route accordingly
    session_ended_by = state.get("session_ended_by") or ""
    if session_ended_by == "TIMEOUT_END":
        return "FEEDBACK"

    discussion_phase_flags = state.get("discussion_assessment") or {}
    if not isinstance(discussion_phase_flags, dict):
        return "PROBLEM_DISCUSSION"

    approach_flags = discussion_phase_flags.get("approach_explained") or {}
    edge_case_flags = discussion_phase_flags.get("edge_cases_discussed") or {}
    complexity_flags = discussion_phase_flags.get("complexity_discussed") or {}

    discussion_turns = state.get("discussion_turns", 0)

    if (
        _is_complete(approach_flags) and
        _is_complete(edge_case_flags) and
        _is_complete(complexity_flags) and
        discussion_turns >= 2
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

    code_submitted_flags = updated_assessment.get("code_submitted") or {}
    walkthrough_flags = updated_assessment.get("walkthrough_provided") or {}
    correctness_flags = updated_assessment.get("correctness_discussed") or {}

    new_turns = state.get("coding_turns", 0) + 1
    user_code = (state.get("user_code") or "").strip()

    is_complete_coding = (
        _is_complete(code_submitted_flags) and
        _is_complete(walkthrough_flags) and
        _is_complete(correctness_flags) and
        new_turns >= 2 and
        len(user_code) > 40
    )

    phase = "REVIEW" if is_complete_coding else "CODING"
    assistant_message = AIMessage(content=res.next_question)

    return {
        "phase": phase,
        "messages": [assistant_message],
        "coding_turns": new_turns,
        "coding_assessment": updated_assessment,
    }


def coding_router(state: InterviewAgentState):

    if state.get("exit_clicked"):
        return "END"

    # Shortcut: if the session was ended by timeout, route accordingly
    session_ended_by = state.get("session_ended_by") or ""
    if session_ended_by == "TIMEOUT_END":
        return "FEEDBACK"

    coding_phase_flags = state.get("coding_assessment") or {}
    if not isinstance(coding_phase_flags, dict):
        return "CODING"

    code_submitted_flags = coding_phase_flags.get("code_submitted") or {}
    walkthrough_flags = coding_phase_flags.get("walkthrough_provided") or {}
    correctness_flags = coding_phase_flags.get("correctness_discussed") or {}

    new_turns = state.get("coding_turns", 0)
    user_code = (state.get("user_code") or "").strip()

    if (
        _is_complete(code_submitted_flags) and
        _is_complete(walkthrough_flags) and
        _is_complete(correctness_flags) and
        new_turns >= 2 and
        len(user_code) > 40
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

    optimization_flags = updated_assessment.get("optimization_discussed") or {}
    edge_case_validation_flags = updated_assessment.get("edge_case_validation") or {}
    final_complexity_flags = updated_assessment.get("final_complexity_summary") or {}

    new_turns = state.get("review_turns", 0) + 1

    is_complete_review = (
        _is_complete(optimization_flags) and
        _is_complete(edge_case_validation_flags) and
        _is_complete(final_complexity_flags) and
        new_turns >= 2
    )

    phase = "FEEDBACK" if is_complete_review else "REVIEW"
    assistant_message = AIMessage(content=res.next_question)

    return {
        "phase": phase,
        "messages": [assistant_message],
        "review_turns": new_turns,
        "review_assessment": updated_assessment,
    }

def review_router(state: InterviewAgentState):
    #end interview if user clicks button
    if state.get("exit_clicked"):
        return "END"


    # Shortcut: if the session was ended by timeout, skip directly to feedback
    session_ended_by = state.get("session_ended_by") or ""
    if session_ended_by == "TIMEOUT_END":
        return "FEEDBACK"

    review_phase_flags = state.get("review_assessment") or {}
    if not isinstance(review_phase_flags, dict):
        return "REVIEW"

    optimization_flags = review_phase_flags.get("optimization_discussed") or {}
    edge_case_validation_flags = review_phase_flags.get("edge_case_validation") or {}
    final_complexity_flags = review_phase_flags.get("final_complexity_summary") or {}

    new_turns = state.get("review_turns", 0)

    if (
        _is_complete(optimization_flags) and
        _is_complete(edge_case_validation_flags) and
        _is_complete(final_complexity_flags) and
        new_turns >= 2
    ):
        return "FEEDBACK"

    return "REVIEW"

def create_fallback_feedback(state: InterviewAgentState) -> FeedbackResponseFormat:
    # Safely get internal assessments
    discussion_assessment = state.get("discussion_assessment") or {}
    coding_assessment = state.get("coding_assessment") or {}
    review_assessment = state.get("review_assessment") or {}

    # Check which criteria were completed
    approach_ok = _is_complete(discussion_assessment.get("approach_explained") or {})
    edge_cases_ok = _is_complete(discussion_assessment.get("edge_cases_discussed") or {})
    complexity_ok = _is_complete(discussion_assessment.get("complexity_discussed") or {})

    code_submitted_ok = _is_complete(coding_assessment.get("code_submitted") or {})
    walkthrough_ok = _is_complete(coding_assessment.get("walkthrough_provided") or {})
    correctness_ok = _is_complete(coding_assessment.get("correctness_discussed") or {})

    optimization_ok = _is_complete(review_assessment.get("optimization_discussed") or {})
    edge_validation_ok = _is_complete(review_assessment.get("edge_case_validation") or {})
    final_complexity_ok = _is_complete(review_assessment.get("final_complexity_summary") or {})

    disc_count = sum([approach_ok, edge_cases_ok, complexity_ok])
    code_count = sum([code_submitted_ok, walkthrough_ok, correctness_ok])
    rev_count = sum([optimization_ok, edge_validation_ok, final_complexity_ok])

    # Dynamic Scoring Heuristics
    ps_score = int(min(10, max(2, 2 + (disc_count * 1.2 + code_count * 1.5))))
    ca_score = int(min(10, max(2, 3 + (3 if complexity_ok else 0) + (4 if final_complexity_ok else 0))))
    comm_score = int(min(10, max(3, 4 + disc_count + rev_count - int(state.get("discussion_turns", 0) // 4))))

    overall_score = int((ps_score * 0.4 + ca_score * 0.3 + comm_score * 0.3) * 10)

    performance_label = "Poor"
    if overall_score >= 90:
        performance_label = "Exceptional"
    elif overall_score >= 75:
        performance_label = "Strong Performance"
    elif overall_score >= 50:
        performance_label = "Adequate"
    elif overall_score >= 35:
        performance_label = "Below Expectations"

    decision = "Strong No Hire"
    if overall_score >= 85:
        decision = "Strong Hire"
    elif overall_score >= 70:
        decision = "Hire"
    elif overall_score >= 55:
        decision = "Lean Hire"
    elif overall_score >= 40:
        decision = "Lean No Hire"
    elif overall_score >= 25:
        decision = "No Hire"

    # Get problem specifics
    problem_references = state.get("problem_references") or {}
    optimal_time = problem_references.get("time_complexity") or "O(N)"
    optimal_space = problem_references.get("space_complexity") or "O(1)"
    problem_title = problem_references.get("title") or "the problem"

    # Heuristic based strengths and weaknesses
    strengths = []
    weaknesses = []

    if approach_ok:
        strengths.append(StrengthItem(
            category="Problem Solving",
            title="Systematic Approach Explanation",
            description="You successfully and clearly explained your approach before jumping into coding.",
            impact="high"
        ))
    else:
        weaknesses.append(WeaknessItem(
            category="Problem Solving",
            title="Premature Implementation Planning",
            description="You struggled to thoroughly explain your approach before starting to write code.",
            severity="medium"
        ))

    if correctness_ok:
        strengths.append(StrengthItem(
            category="Technical Execution",
            title="Logic Correctness Verification",
            description="Your implementation correctly handled standard test scenarios discussed.",
            impact="high"
        ))
    else:
        weaknesses.append(WeaknessItem(
            category="Technical Execution",
            title="Edge Case Logic Gaps",
            description="Your implementation had logic gaps under edge cases or extreme input parameters.",
            severity="high"
        ))

    if optimization_ok:
        strengths.append(StrengthItem(
            category="Optimization",
            title="Proactive Resource Optimization",
            description="You actively identified performance bottlenecks and optimized space/time complexities.",
            impact="medium"
        ))
    else:
        weaknesses.append(WeaknessItem(
            category="Optimization",
            title="Suboptimal Approach Selection",
            description="The chosen approach contains suboptimal memory allocations or extra passes.",
            severity="medium"
        ))

    if not strengths:
        strengths.append(StrengthItem(
            category="Communication",
            title="Interactive Discussion Participation",
            description="You maintained an active dialogue with the interviewer throughout the session.",
            impact="low"
        ))
    if not weaknesses:
        weaknesses.append(WeaknessItem(
            category="Problem Solving",
            title="Alternative Approaches Comparison",
            description="Try exploring alternative data structures to compare performance trade-offs in depth.",
            severity="low"
        ))

    # Time spent
    total_time = state.get("total_time_spent_sec") or 0
    total_submissions = state.get("total_submissions") or 0
    hints_used = state.get("hints_used") or 0

    speed_percentile = max(0, min(100, 100 - int((total_time / 1800) * 100))) if total_time > 0 else 50

    return FeedbackResponseFormat(
        response=(
            f"Thank you for completing the technical interview on '{problem_title}'. "
            f"We have compiled your comprehensive technical performance report. "
            f"You demonstrated an overall score of {overall_score}/100. "
            f"Please review the detailed category breakdowns, metrics, strengths, and areas for improvement below."
        ),
        feedback=FeedbackItem(
            session_summary=SessionSummary(
                overall_score=overall_score,
                performance_label=performance_label,
                difficulty=problem_references.get("difficulty") or "Medium",
                time_spent_seconds=total_time
            ),
            scores=Scores(
                problem_solving=ScoreWithNotes(
                    score=ps_score,
                    notes=f"Demonstrated good approach explaining and coding capabilities with {code_count}/3 coding milestones met."
                ),
                complexity_analysis=ComplexityScore(
                    score=ca_score,
                    time_complexity=optimal_time,
                    space_complexity=optimal_space,
                    notes=f"Identified optimal complexity bounds. Phase metrics: discussion={complexity_ok}, final review={final_complexity_ok}."
                ),
                communication=ScoreWithNotes(
                    score=comm_score,
                    notes="Structured dialogue, active engagement with the interviewer prompt constraints."
                )
            ),
            strengths=strengths,
            weaknesses=weaknesses,
            key_metrics=KeyMetrics(
                runtime_complexity=ComplexityMetric(
                    value=optimal_time,
                    status="optimal" if optimization_ok else "acceptable"
                ),
                memory_efficiency=ComplexityMetric(
                    value=optimal_space,
                    status="optimal" if final_complexity_ok else "acceptable"
                ),
                coding_speed_percentile=speed_percentile
            ),
            final_verdict=Verdict(
                decision=decision,
                confidence=0.8,
                summary=f"Candidate performance was analyzed. Overall hiring recommendation is {decision} with 80% confidence assessment."
            )
        )
    )

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
    time_expired = bool(state.get("time_expired") or False)
    extra_time_used = bool(state.get("extra_time_used") or False)
    extension_count = int(state.get("extension_count") or 0)
    session_ended_by = state.get("session_ended_by") or "NORMAL"

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
        f"Time expired: {time_expired}\n"
        f"Extra time used: {extra_time_used}\n"
        f"Extension count: {extension_count}\n"
        f"Session ended by: {session_ended_by}\n"
    )

    try:
        res = base_llm.with_structured_output(
            FeedbackResponseFormat
        ).invoke([
            SystemMessage(content=final_prompt),
            *messages[-6:],
            context_message,
        ])
        if res is None:
            raise ValueError("Structured LLM returned None")
    except Exception as exc:
        print(f"Structured feedback generation failed: {exc}. Using dynamic fallback compilation.")
        res = create_fallback_feedback(state)

    assistant_message = AIMessage(content=res.response)
    
    fb_dict = res.feedback.model_dump()
    fb_dict["session_summary"]["time_spent_seconds"] = total_time

    return {
        "messages": [assistant_message],
        "phase": "FEEDBACK",
        "feedback": fb_dict,
    }

#-------------------------------------------------------
#compiling the graph:

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


def init_agent_graph() -> bool:
    global _pg_pool, checkpointer, graph

    if graph is not None:
        return True

    db_url = os.getenv("DB_URL")
    if not db_url:
        print("AI agent init skipped: DB_URL is not configured")
        return False

    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg_pool import ConnectionPool
        from psycopg.rows import dict_row

        _pg_pool = ConnectionPool(
            conninfo=db_url,
            kwargs={"autocommit": True, "row_factory": dict_row},
            min_size=1,
            max_size=10,
            max_lifetime=300.0,
            max_idle=30.0,
            check=ConnectionPool.check_connection,
        )
        checkpointer = PostgresSaver(conn=_pg_pool)
        checkpointer.setup()
        graph = create_interview_graph(checkpointer)
        return True
    except Exception as exc:
        print(f"AI agent init failed: {exc}")
        graph = None
        checkpointer = None
        if _pg_pool is not None:
            try:
                _pg_pool.close()
            except Exception:
                pass
            _pg_pool = None
        return False


def get_graph():
    if graph is None:
        raise RuntimeError("AI agent graph is unavailable")
    return graph


def is_agent_available() -> bool:
    return graph is not None


def clear_agent_checkpoints(session_id: str) -> bool:
    return clear_interview_checkpoints(checkpointer, session_id)


def close_agent_graph() -> None:
    global _pg_pool, checkpointer, graph

    graph = None
    checkpointer = None
    if _pg_pool is not None:
        try:
            _pg_pool.close()
        except Exception:
            pass
    _pg_pool = None
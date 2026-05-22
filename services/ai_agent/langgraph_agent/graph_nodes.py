from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..schemas import (
    CodingAssessment,
    DiscussionAssessment,
    FeedbackItem,
    FeedbackResponseFormat,
    KeyMetrics,
    ReviewAssessment,
    ScoreWithNotes,
    Scores,
    SessionSummary,
    StrengthItem,
    Verdict,
    WeaknessItem,
    ComplexityMetric,
    ComplexityScore,
)
from ..system_prompt import (
    CODING_PROMPT,
    FEEDBACK_PROMPT,
    INTERVIEW_INIT_PROMPT,
    PROBLEM_DISCUSSION_PROMPT,
    REVIEW_PROMPT,
)
from .criteria import _is_complete, _merge_criterion
from .llm import base_llm
from .prompt_context import build_complete_prompt


def interview_init_node(state):
    existing_messages = list(state.get("messages", []))
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
        "messages": [res],
    }


def problem_discussion_phase_node(state):
    final_prompt = build_complete_prompt(state, PROBLEM_DISCUSSION_PROMPT)
    messages = state.get("messages", [])

    if not messages or not isinstance(messages[-1], HumanMessage):
        return {}

    res: DiscussionAssessment = base_llm.with_structured_output(DiscussionAssessment).invoke(
        [SystemMessage(content=final_prompt), *messages[-6:]]
    )

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
        _is_complete(approach_flags)
        and _is_complete(edge_case_flags)
        and _is_complete(complexity_flags)
        and new_turns >= 2
    )

    phase = "CODING" if is_complete_discussion else "PROBLEM_DISCUSSION"
    assistant_message = AIMessage(content=res.next_question)

    return {
        "phase": phase,
        "messages": [assistant_message],
        "discussion_turns": new_turns,
        "discussion_assessment": updated_assessment,
    }


def discussion_router(state):
    if state.get("exit_clicked"):
        return "END"

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
        _is_complete(approach_flags)
        and _is_complete(edge_case_flags)
        and _is_complete(complexity_flags)
        and discussion_turns >= 2
    ):
        return "CODING"

    return "PROBLEM_DISCUSSION"


def coding_phase_node(state):
    final_prompt = build_complete_prompt(state, CODING_PROMPT)
    messages = state.get("messages", [])

    if not messages or not isinstance(messages[-1], HumanMessage):
        return {}

    res: CodingAssessment = base_llm.with_structured_output(CodingAssessment).invoke(
        [SystemMessage(content=final_prompt), *messages[-6:]]
    )

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
        _is_complete(code_submitted_flags)
        and _is_complete(walkthrough_flags)
        and _is_complete(correctness_flags)
        and new_turns >= 2
        and len(user_code) > 40
    )

    phase = "REVIEW" if is_complete_coding else "CODING"
    assistant_message = AIMessage(content=res.next_question)

    return {
        "phase": phase,
        "messages": [assistant_message],
        "coding_turns": new_turns,
        "coding_assessment": updated_assessment,
    }


def coding_router(state):
    if state.get("exit_clicked"):
        return "END"

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
        _is_complete(code_submitted_flags)
        and _is_complete(walkthrough_flags)
        and _is_complete(correctness_flags)
        and new_turns >= 2
        and len(user_code) > 40
    ):
        return "REVIEW"

    return "CODING"


def review_phase_node(state):
    final_prompt = build_complete_prompt(state, REVIEW_PROMPT)
    messages = state.get("messages", [])

    if not messages or not isinstance(messages[-1], HumanMessage):
        return {}

    res: ReviewAssessment = base_llm.with_structured_output(ReviewAssessment).invoke(
        [SystemMessage(content=final_prompt), *messages[-6:]]
    )

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
        _is_complete(optimization_flags)
        and _is_complete(edge_case_validation_flags)
        and _is_complete(final_complexity_flags)
        and new_turns >= 2
    )

    phase = "FEEDBACK" if is_complete_review else "REVIEW"
    assistant_message = AIMessage(content=res.next_question)

    return {
        "phase": phase,
        "messages": [assistant_message],
        "review_turns": new_turns,
        "review_assessment": updated_assessment,
    }


def review_router(state):
    if state.get("exit_clicked"):
        return "END"

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
        _is_complete(optimization_flags)
        and _is_complete(edge_case_validation_flags)
        and _is_complete(final_complexity_flags)
        and new_turns >= 2
    ):
        return "FEEDBACK"

    return "REVIEW"


def _get_elapsed_time(state) -> int:
    total_time = state.get("total_time_spent_sec") or 0
    if total_time <= 0:
        try:
            import uuid
            from sqlmodel import Session
            from modules.db import engine
            from helpers.session.get_session_data import fetch_session_timer
            
            session_id_str = state.get("session_id")
            if session_id_str:
                session_uuid = uuid.UUID(session_id_str)
                with Session(engine) as db:
                    session_timer = fetch_session_timer(db, session_uuid)
                    if session_timer:
                        total_time = int(
                            session_timer["expected_time"] * 60
                            - session_timer["remaining_time"]
                        )
                        if total_time < 0:
                            total_time = 0
        except Exception as exc:
            print(f"Self-healing time calculation failed: {exc}")
    return total_time


def create_fallback_feedback(state):
    discussion_assessment = state.get("discussion_assessment") or {}
    coding_assessment = state.get("coding_assessment") or {}
    review_assessment = state.get("review_assessment") or {}

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

    problem_references = state.get("problem_references") or {}
    optimal_time = problem_references.get("time_complexity") or "O(N)"
    optimal_space = problem_references.get("space_complexity") or "O(1)"
    problem_title = problem_references.get("title") or "the problem"

    strengths = []
    weaknesses = []

    if approach_ok:
        strengths.append(
            StrengthItem(
                category="Problem Solving",
                title="Systematic Approach Explanation",
                description="You successfully and clearly explained your approach before jumping into coding.",
                impact="high",
            )
        )
    else:
        weaknesses.append(
            WeaknessItem(
                category="Problem Solving",
                title="Premature Implementation Planning",
                description="You struggled to thoroughly explain your approach before starting to write code.",
                severity="medium",
            )
        )

    if correctness_ok:
        strengths.append(
            StrengthItem(
                category="Technical Execution",
                title="Logic Correctness Verification",
                description="Your implementation correctly handled standard test scenarios discussed.",
                impact="high",
            )
        )
    else:
        weaknesses.append(
            WeaknessItem(
                category="Technical Execution",
                title="Edge Case Logic Gaps",
                description="Your implementation had logic gaps under edge cases or extreme input parameters.",
                severity="high",
            )
        )

    if optimization_ok:
        strengths.append(
            StrengthItem(
                category="Optimization",
                title="Proactive Resource Optimization",
                description="You actively identified performance bottlenecks and optimized space/time complexities.",
                impact="medium",
            )
        )
    else:
        weaknesses.append(
            WeaknessItem(
                category="Optimization",
                title="Suboptimal Approach Selection",
                description="The chosen approach contains suboptimal memory allocations or extra passes.",
                severity="medium",
            )
        )

    if not strengths:
        strengths.append(
            StrengthItem(
                category="Communication",
                title="Interactive Discussion Participation",
                description="You maintained an active dialogue with the interviewer throughout the session.",
                impact="low",
            )
        )
    if not weaknesses:
        weaknesses.append(
            WeaknessItem(
                category="Problem Solving",
                title="Alternative Approaches Comparison",
                description="Try exploring alternative data structures to compare performance trade-offs in depth.",
                severity="low",
            )
        )

    total_time = _get_elapsed_time(state)
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
                time_spent_seconds=total_time,
            ),
            scores=Scores(
                problem_solving=ScoreWithNotes(
                    score=ps_score,
                    notes=f"Demonstrated good approach explaining and coding capabilities with {code_count}/3 coding milestones met.",
                ),
                complexity_analysis=ComplexityScore(
                    score=ca_score,
                    time_complexity=optimal_time,
                    space_complexity=optimal_space,
                    notes=f"Identified optimal complexity bounds. Phase metrics: discussion={complexity_ok}, final review={final_complexity_ok}.",
                ),
                communication=ScoreWithNotes(
                    score=comm_score,
                    notes="Structured dialogue, active engagement with the interviewer prompt constraints.",
                ),
            ),
            strengths=strengths,
            weaknesses=weaknesses,
            key_metrics=KeyMetrics(
                runtime_complexity=ComplexityMetric(
                    value=optimal_time,
                    status="optimal" if optimization_ok else "acceptable",
                ),
                memory_efficiency=ComplexityMetric(
                    value=optimal_space,
                    status="optimal" if final_complexity_ok else "acceptable",
                ),
                coding_speed_percentile=speed_percentile,
            ),
            final_verdict=Verdict(
                decision=decision,
                confidence=0.8,
                summary=f"Candidate performance was analyzed. Overall hiring recommendation is {decision} with 80% confidence assessment.",
            ),
        ),
    )


def feedback_phase_node(state):
    final_prompt = build_complete_prompt(state, FEEDBACK_PROMPT)
    messages = state.get("messages", [])
    if not messages:
        return {}

    discussion_assessment = state.get("discussion_assessment") or {}
    coding_assessment = state.get("coding_assessment") or {}
    review_assessment = state.get("review_assessment") or {}

    total_time = _get_elapsed_time(state)
    total_submissions = state.get("total_submissions") or 0
    hints_used = state.get("hints_used") or 0
    time_expired = bool(state.get("time_expired") or False)
    extra_time_used = bool(state.get("extra_time_used") or False)
    extension_count = int(state.get("extension_count") or 0)
    session_ended_by = state.get("session_ended_by") or "NORMAL"

    context_message = HumanMessage(
        content=(
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
    )

    try:
        res = base_llm.with_structured_output(FeedbackResponseFormat).invoke(
            [SystemMessage(content=final_prompt), *messages[-6:], context_message]
        )
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

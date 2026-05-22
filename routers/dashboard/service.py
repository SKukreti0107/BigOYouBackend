from modules.db import engine, Session_Feedback, Interview_Session, Problems
from sqlmodel import Session, select
import uuid
from datetime import datetime, timezone, timedelta

def calculate_streak(db: Session, user_uuid: uuid.UUID) -> int:
    """Count consecutive days with at least one COMPLETED interview (has feedback)."""
    try:
        # Only count sessions that have feedback (i.e., actually completed)
        stmt = (
            select(Interview_Session.started_at)
            .join(Session_Feedback, Session_Feedback.session_id == Interview_Session.session_id)
            .where(Interview_Session.user_id == user_uuid)
            .order_by(Interview_Session.started_at.asc())
        )
        results = db.exec(stmt).all()
        if not results:
            return 0

        # Extract dates and convert to unique sorted list of date objects
        unique_dates = sorted(list({d.date() for d in results}))
        if not unique_dates:
            return 0

        today = datetime.utcnow().date()
        
        # If the last activity was more than 1 day ago, the streak is broken (0)
        if (today - unique_dates[-1]).days > 1:
            return 0

        streak = 1
        curr = unique_dates[-1]
        
        # Count backwards for consecutive days
        for d in reversed(unique_dates[:-1]):
            diff = (curr - d).days
            if diff == 1:
                streak += 1
                curr = d
            elif diff == 0:
                continue
            else:
                break
        return streak
    except Exception as e:
        print(f"Error calculating streak: {e}")
        return 0

def fetch_quick_stats(db: Session, user_uuid: uuid.UUID) -> dict:
    """Only count sessions that have feedback as 'completed' interviews."""
    try:
        # Completed sessions = sessions that have a Session_Feedback row
        completed_stmt = (
            select(Interview_Session)
            .join(Session_Feedback, Session_Feedback.session_id == Interview_Session.session_id)
            .where(Interview_Session.user_id == user_uuid)
        )
        completed_sessions = db.exec(completed_stmt).all()
        interviews_taken = len(completed_sessions)

        # Count completed interviews this week (last 7 days)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        week_sessions = [s for s in completed_sessions if s.started_at >= seven_days_ago]
        interviews_this_week = len(week_sessions)

        # Get feedback scores
        feedback_stmt = (
            select(Session_Feedback.final_score)
            .join(Interview_Session, Interview_Session.session_id == Session_Feedback.session_id)
            .where(Interview_Session.user_id == user_uuid)
            .order_by(Session_Feedback.created_at.desc())
        )
        scores = db.exec(feedback_stmt).all()
        scores = [s for s in scores if s is not None]

        if scores:
            avg_score = round(sum(scores) / len(scores), 1)
            if len(scores) >= 2:
                latest_score = scores[0]
                prev_avg = sum(scores[1:]) / len(scores[1:])
                score_improvement = round(latest_score - prev_avg, 1)
            else:
                score_improvement = 0.0
        else:
            avg_score = 0.0
            score_improvement = 0.0

        # Calculate Top Topics (only from completed sessions)
        topics = [s.topic for s in completed_sessions if s.topic]
        from collections import Counter
        topic_counts = Counter(topics)
        top_topics = [topic for topic, _ in topic_counts.most_common(3)]

        return {
            "interviews_taken": interviews_taken,
            "interviews_this_week": interviews_this_week,
            "average_score": avg_score,
            "score_improvement": score_improvement,
            "top_topics": top_topics
        }
    except Exception as e:
        print(f"Error fetching quick stats: {e}")
        return {
            "interviews_taken": 0,
            "interviews_this_week": 0,
            "average_score": 0.0,
            "score_improvement": 0.0,
            "top_topics": []
        }

def fetch_score_trend(db: Session, user_uuid: uuid.UUID) -> list:
    try:
        stmt = (
            select(Session_Feedback.final_score, Problems.difficulty, Session_Feedback.created_at)
            .join(Interview_Session, Interview_Session.session_id == Session_Feedback.session_id)
            .join(Problems, Problems.problem_id == Interview_Session.problem_id)
            .where(Interview_Session.user_id == user_uuid)
            .order_by(Session_Feedback.created_at.asc())
            .limit(10)
        )
        results = db.exec(stmt).all()
        
        sessions_trend = []
        for idx, (score, diff, created_at) in enumerate(results):
            if score is None:
                continue
            sessions_trend.append({
                "session_number": idx + 1,
                "score": score,
                "difficulty": diff,
                "date": created_at.strftime("%Y-%m-%d")
            })
        return sessions_trend
    except Exception as e:
        print(f"Error fetching score trend: {e}")
        return []

def get_improvement_tip(topic: str) -> str:
    topic_lower = topic.lower()
    if "dynamic" in topic_lower or "dp" in topic_lower:
        return "State transitions & overlapping subproblems."
    elif "graph" in topic_lower or "tree" in topic_lower:
        return "DFS/BFS traversals, cycle detection, & height logic."
    elif "array" in topic_lower or "string" in topic_lower:
        return "Sliding window, two-pointer techniques, & boundary cases."
    elif "sort" in topic_lower or "search" in topic_lower:
        return "Divide & conquer, binary search, & recursion limits."
    elif "recursion" in topic_lower or "backtrack" in topic_lower:
        return "Pruning search space & base case conditions."
    elif "design" in topic_lower or "system" in topic_lower:
        return "Scalability patterns & partition sharding."
    else:
        return "Boundary checking and time/space complexity optimization."

def fetch_weak_areas(db: Session, user_uuid: uuid.UUID) -> list:
    try:
        stmt = (
            select(Interview_Session.topic, Session_Feedback.final_score)
            .join(Interview_Session, Interview_Session.session_id == Session_Feedback.session_id)
            .where(Interview_Session.user_id == user_uuid)
        )
        results = db.exec(stmt).all()
        
        # Group scores by topic
        topic_scores = {}
        for topic, score in results:
            if not topic or score is None:
                continue
            if topic not in topic_scores:
                topic_scores[topic] = []
            topic_scores[topic].append(score)
            
        weak_areas = []
        for topic, scores in topic_scores.items():
            avg = round(sum(scores) / len(scores), 1)
            # We flag anything below 75 as a weak area
            if avg < 75:
                weak_areas.append({
                    "topic": topic,
                    "success_rate": int(avg),
                    "improvement_tip": get_improvement_tip(topic)
                })
                
        # Sort by success rate ascending (lowest score first)
        weak_areas = sorted(weak_areas, key=lambda x: x["success_rate"])
        return weak_areas[:3]
    except Exception as e:
        print(f"Error fetching weak areas: {e}")
        return []

def fetch_last_interview_feedback(db: Session, user_uuid: uuid.UUID) -> dict:
    try:
        stmt = (
            select(Session_Feedback.feedback_json, Session_Feedback.final_score)
            .join(Interview_Session, Interview_Session.session_id == Session_Feedback.session_id)
            .where(Interview_Session.user_id == user_uuid)
            .order_by(Interview_Session.started_at.desc())
            .limit(1)
        )
        result = db.exec(stmt).first()

        if not result:
            return {}

        feedback_json, final_score = result

        # Robust extraction in case the dictionary has an outer "feedback" key
        fb_data = feedback_json.get("feedback", {}) if "feedback" in feedback_json else feedback_json

        # Retrieve score from final_score column, then try nested overall_score
        score = final_score
        if score is None:
            score = fb_data.get("session_summary", {}).get("overall_score")
        if score is None:
            score = fb_data.get("overall_score", 0)

        return {
            "strengths": fb_data.get("strengths", []),
            "weaknesses": fb_data.get("weaknesses", []),
            "score": score
        }
    except Exception as e:
        print(f"Error fetching last feedback: {e}")
        return {}


def fetch_paused_session(db: Session, user_uuid: uuid.UUID) -> dict | None:
    """Find an ACTIVE session that the user disconnected from.

    A session is considered "paused" when:
      - status == ACTIVE
      - phase != FEEDBACK (not yet finished)
    
    The session remains recoverable for 30 minutes after the interview
    timer would have naturally expired.  After that we auto-terminate.
    """
    try:
        stmt = (
            select(Interview_Session, Problems)
            .join(Problems, Interview_Session.problem_id == Problems.problem_id)
            .where(
                Interview_Session.user_id == user_uuid,
                Interview_Session.status == "ACTIVE",
                Interview_Session.phase != "FEEDBACK",
            )
            .order_by(Interview_Session.started_at.desc())
            .limit(1)
        )
        result = db.exec(stmt).first()
        if not result:
            return None

        session_row, problem_row = result

        # Compute when the interview timer expires
        # (started_at + expected_time in minutes)
        timer_end = session_row.started_at + timedelta(minutes=problem_row.expected_time)

        # Try to account for LangGraph extensions if available
        try:
            from services.ai_agent.langgraph_agent import get_graph
            graph = get_graph()
            config = {"configurable": {"thread_id": str(session_row.session_id)}}
            snapshot = graph.get_state(config)
            values = snapshot.values if snapshot and hasattr(snapshot, "values") else {}
            extension_count = int(values.get("extension_count") or 0)
            if extension_count > 0:
                timer_end += timedelta(minutes=extension_count * 15)
        except Exception:
            pass

        # Add 30-min grace period
        grace_deadline = timer_end + timedelta(minutes=30)
        now = datetime.now(timezone.utc)

        # Handle naive datetimes from DB
        if session_row.started_at.tzinfo is None:
            now = datetime.utcnow()

        seconds_remaining = (grace_deadline - now).total_seconds()

        if seconds_remaining <= 0:
            # Grace period expired → auto-terminate
            session_row.status = "TERMINATED"
            db.add(session_row)
            db.commit()
            return None

        return {
            "session_id": str(session_row.session_id),
            "topic": session_row.topic,
            "phase": session_row.phase,
            "problem_title": problem_row.title,
            "difficulty": problem_row.difficulty,
            "expected_time": problem_row.expected_time,
            "seconds_remaining": int(seconds_remaining),
            "started_at": session_row.started_at.isoformat(),
        }
    except Exception as e:
        print(f"Error fetching paused session: {e}")
        return None

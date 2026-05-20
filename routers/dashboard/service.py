from modules.db import engine, Session_Feedback, Interview_Session, Problems
from sqlmodel import Session, select
import uuid
from datetime import datetime, timedelta

def calculate_streak(db: Session, user_uuid: uuid.UUID) -> int:
    try:
        stmt = (
            select(Interview_Session.started_at)
            .where(Interview_Session.user_id == user_uuid)
            .order_by(Interview_Session.started_at.asc())
        )
        results = db.exec(stmt).all()
        if not results:
            return 0

        # Extract dates and convert to unique sorted list of date objects
        unique_dates = sorted(list({d.started_at.date() for d in results}))
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
    try:
        sessions_stmt = select(Interview_Session).where(Interview_Session.user_id == user_uuid)
        sessions = db.exec(sessions_stmt).all()
        interviews_taken = len(sessions)

        # Count interviews this week (last 7 days)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        week_sessions = [s for s in sessions if s.started_at >= seven_days_ago]
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

        # Calculate Top Topics
        topics = [s.topic for s in sessions if s.topic]
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
            select(Session_Feedback.feedback_json)
            .join(Interview_Session, Interview_Session.session_id == Session_Feedback.session_id)
            .where(Interview_Session.user_id == user_uuid)
            .order_by(Session_Feedback.created_at.desc())
            .limit(1)
        )
        feedback = db.exec(stmt).first()

        if not feedback:
            return {}

        feedback_json = feedback[0] if isinstance(feedback, tuple) else feedback

        return {
            "strengths": feedback_json.get("strengths", []),
            "weaknesses": feedback_json.get("weaknesses", []),
            "score": feedback_json.get("overall_score", 0)
        }
    except Exception as e:
        print(f"Error fetching last feedback: {e}")
        return {}

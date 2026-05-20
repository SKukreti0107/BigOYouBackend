import uuid
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from helpers.auth.auth_deps import get_current_user
from modules.db import engine, Problems, Problem_topics, Interview_Session, Session_Feedback

router = APIRouter()

@router.get("/problems")
def get_problems(user_id: str = Depends(get_current_user)):
    try:
        user_id = uuid.UUID(user_id)
        with Session(engine) as session:
            statement = (
                select(
                    Problem_topics.topic,
                    Problems.problem_id,
                    Problems.title,
                    Interview_Session.status,
                    Session_Feedback.final_score
                )
                .select_from(Problem_topics)
                .join(Problems, Problem_topics.problem_id == Problems.problem_id)
                .outerjoin(
                    Interview_Session,
                    (Interview_Session.problem_id == Problems.problem_id)
                    & (Interview_Session.user_id == user_id)
                )
                .outerjoin(
                    Session_Feedback,
                    Session_Feedback.session_id == Interview_Session.session_id
                )
            )

            rows = session.exec(statement).all()
            
            # Group by topic, then by problem_id to handle multiple sessions per problem
            topics_map = {}
            for row in rows:
                topic = row[0]
                prob_id = row[1]
                title = row[2]
                status = row[3]
                score = row[4]
                
                if topic not in topics_map:
                    topics_map[topic] = {}
                
                prob_id_str = str(prob_id)
                if prob_id_str not in topics_map[topic]:
                    topics_map[topic][prob_id_str] = {
                        "problem_id": prob_id_str,
                        "title": title,
                        "sessions": []
                    }
                
                if status is not None:
                    topics_map[topic][prob_id_str]["sessions"].append({
                        "status": status,
                        "score": score
                    })

            payload = []
            for topic, p_dict in topics_map.items():
                problems_list = []
                completed_count = 0
                total_count = len(p_dict)
                
                for p_id, p_info in p_dict.items():
                    sessions_list = p_info["sessions"]
                    is_completed = False
                    is_reattempt = False
                    highest_score = None
                    
                    for s in sessions_list:
                        score = s["score"]
                        status = s["status"]
                        
                        if score is not None:
                            if highest_score is None or score > highest_score:
                                highest_score = score
                                
                        # Question is completed only if session status is CLOSED and score is strictly > 70
                        if status == "CLOSED" and score is not None:
                            if score > 70:
                                is_completed = True
                                
                    # If not completed, it is a Suggested Reattempt if at least one session is CLOSED and score <= 70
                    if not is_completed:
                        for s in sessions_list:
                            status = s["status"]
                            score = s["score"]
                            if status == "CLOSED" and score is not None and score <= 70:
                                is_reattempt = True
                                break
                                
                    if is_completed:
                        completed_count += 1
                        
                    problems_list.append({
                        "id": p_id, # Frontend uses p.id, so we return it as "id"
                        "title": p_info["title"],
                        "is_completed": is_completed,
                        "is_reattempt": is_reattempt,
                        "score": highest_score
                    })
                
                # Sort problems by title for consistency
                problems_list = sorted(problems_list, key=lambda x: x["title"])
                
                payload.append({
                    "topic": topic,
                    "total": total_count,
                    "completed": completed_count,
                    "problems": problems_list
                })
                
            # Sort topics alphabetically
            payload = sorted(payload, key=lambda x: x["topic"])
            return payload

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"error fetching problems: {e}")

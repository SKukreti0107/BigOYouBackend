from modules.db import engine,Problems,Problem_topics,User_Problem_Status
from fastapi import APIRouter,HTTPException,Response,Depends
from helpers.auth_deps import get_current_user
from sqlmodel import Session,select
from sqlalchemy import func,case
import uuid

router = APIRouter()

@router.get("/problems")
def get_problems(user_id:str = Depends(get_current_user)):
    try:
        user_id = uuid.UUID(user_id)
        with Session(engine) as session :
            statement = (select(Problem_topics.topic,
                                func.count(Problems.problem_id).label("total"),
                                func.count(
                                    case((User_Problem_Status.is_completed == True, 1))
                                ).label("completed"),
                                func.json_agg(
                                    func.json_build_object(
                                        "problem_id", Problems.problem_id,
                                        "title", Problems.title,
                                        "is_completed", func.coalesce(User_Problem_Status.is_completed, False)
                                    )
                                ).label("problems"),
                                )
                                .select_from(Problem_topics)
                                .join(Problems,Problem_topics.problem_id==Problems.problem_id)
                                .outerjoin(User_Problem_Status,(User_Problem_Status.problem_id == Problems.problem_id)
                                           & (User_Problem_Status.user_id == user_id),
                                           )
                                           .group_by(Problem_topics.topic)
                                )
            
            rows = session.exec(statement).all()
            # print(rows)
            return [
                {
                    "topic":row.topic,
                    "total":row.total,
                    "completed":row.completed,
                    "problems":row.problems,
                }
                for row in rows
                
            ]
    
    except ValueError:
        raise HTTPException(status_code=400,detail="Invalid user_id")
    except Exception as e:
        raise HTTPException(status_code=500,detail=f"error fetching problems: {e}")
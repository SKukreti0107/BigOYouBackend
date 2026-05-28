from fastapi import APIRouter, HTTPException, Depends

from helpers.redis.redis_client import task_queue
from helpers.session.update_sesson_metrics import populate_time_to_first_submission_sec, increment_total_submissions
from helpers.auth.auth_deps import get_current_user
from modules.schemas import ExecuteRequest
from services.code_runner.worker import run_code


router = APIRouter()


@router.post("/execute")
def execute_user_code(req: ExecuteRequest, user_id: str = Depends(get_current_user)):
    import time
    import uuid
    from sqlmodel import Session
    from modules.db import engine, Interview_Session, Problems
    from services.code_runner.template_generator import generate_wrapper

    populate_time_to_first_submission_sec(req.session_id, user_id)
    increment_total_submissions(req.session_id, user_id)

    code_to_run = req.code
    try:
        with Session(engine) as db:
            session_uuid = uuid.UUID(req.session_id)
            session_row = db.get(Interview_Session, session_uuid)
            if session_row:
                problem = db.get(Problems, session_row.problem_id)
                if problem and problem.meta_data:
                    # Prefer example_testcases, then sample_testcase, fallback to example
                    testcase_str = problem.example_testcases or problem.sample_testcase or problem.example
                    if testcase_str:
                        code_to_run = generate_wrapper(
                            user_code=req.code,
                            language=req.language,
                            meta_data=problem.meta_data,
                            testcase_str=testcase_str
                        )
    except Exception as e:
        print(f"Error wrapping code for execution: {e}")

    job = task_queue.enqueue(
        run_code,
        code=code_to_run,
        language=req.language,
        job_timeout=5
    )

    for _ in range(30):
        job.refresh()
        if job.is_finished:
            return job.result
        if job.is_failed:
            raise HTTPException(status_code=500, detail="Job failed")
        time.sleep(0.1)

    raise HTTPException(status_code=202, detail="Job queued, result not ready")

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

    populate_time_to_first_submission_sec(req.session_id, user_id)
    increment_total_submissions(req.session_id, user_id)

    job = task_queue.enqueue(
        run_code,
        code=req.code,
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

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from helpers.redis_client import task_queue
from helpers.populate_sesson_metrics import populate_time_to_first_submission_sec,increment_total_submissions
from services.code_runner.worker import run_code
from helpers.auth_deps import get_current_user

class ExecuteRequest(BaseModel):
    language:str
    code:str
    session_id:str


router = APIRouter()

##testing for now
@router.post("/execute")
def execute_user_code(req:ExecuteRequest, user_id: str = Depends(get_current_user)):
    import time

    ## check for first time code run , update time_to_first_submission_sec 
    ## count total_submissions
    populate_time_to_first_submission_sec(req.session_id, user_id)
    increment_total_submissions(req.session_id, user_id)

    job = task_queue.enqueue(
        run_code,
        code = req.code,
        language=req.language,
        job_timeout=5
    )

    # Poll for result (max 10 seconds)
    for _ in range(30):
        job.refresh()
        if job.is_finished:
            return job.result
        if job.is_failed:
            raise HTTPException(status_code=500, detail="Job failed")
        time.sleep(0.1)

    raise HTTPException(status_code=202, detail="Job queued, result not ready")

   

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from helpers.redis_client import task_queue
from services.code_runner.worker import run_code

class ExecuteRequest(BaseModel):
    language:str
    code:str


router = APIRouter()

##testing for now
@router.post("/execute")
def execute_user_code(req:ExecuteRequest):
    import time

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

   

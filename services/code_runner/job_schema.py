from pydantic import BaseModel

class CodeRunJob(BaseModel):
    job_id: str
    language: str
    code: str

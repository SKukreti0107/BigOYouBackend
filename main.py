from fastapi import FastAPI
from modules.auth import router as auth_router
from modules.problems import router as problem_router
from modules.interview import router as interview_router
from modules.execute_code import router as code_execute_router
from modules.interview_agent import router as agent_router
from modules.db import create_db_and_table
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI(title="BigO(you)",version="1.0.0")
import os 
from dotenv import load_dotenv
load_dotenv()

ENV = os.getenv("ENV","dev")
DEBUG = ENV == "dev"

origins = os.getenv("ALLOWED_ORIGINS","http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins = origins,
    allow_credentials = True,
    allow_methods =["*"],
    allow_headers = ["*"],
)

@app.on_event("startup")
def on_startup():
    create_db_and_table()

@app.get("/")
def root():
    return {
        "message":"api system working"
    }


app.include_router(auth_router)
app.include_router(problem_router)
app.include_router(interview_router)
app.include_router(code_execute_router)
app.include_router(agent_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=DEBUG)
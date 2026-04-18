from fastapi import FastAPI
from routers.auth import router as auth_router
from routers.problems import router as problem_router
from routers.interview import router as interview_router
from routers.execute_code import router as code_execute_router
from routers.interview_agent import router as agent_router
from modules.db import create_db_and_table
from fastapi.middleware.cors import CORSMiddleware
import os 
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from services.ai_agent.langgraph_agent import close_agent_graph, init_agent_graph

from modules.db import engine
from helpers.redis.redis_client import redis_conn
load_dotenv()



ENV = os.getenv("ENV","dev")
DEBUG = ENV == "dev"

@asynccontextmanager
async def lifespan(app:FastAPI):
    create_db_and_table()
    app.state.ai_agent_available = init_agent_graph()
    if not app.state.ai_agent_available:
        print("AI agent unavailable at startup; interview-agent endpoints will return 503")
    yield
    #any shutdown cleanup can go here 
    print("Shutting down application....")
    close_agent_graph()
    engine.dispose()
    redis_conn.close()

app = FastAPI(title="BigO(you)",version="1.0.0",lifespan=lifespan)


origins = os.getenv("ALLOWED_ORIGINS","http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins = origins,
    allow_credentials = True,
    allow_methods =["*"],
    allow_headers = ["*"],
)

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
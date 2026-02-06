import uuid
from modules.db import engine,Users
from fastapi import APIRouter,HTTPException,Response,Depends
from helpers.pass_hash import hash_password,verify_password
from helpers.gen_JWT_token import create_token,decode_token
from helpers.auth_deps import get_current_user
from sqlmodel import Session,select

from pydantic import BaseModel

class LoginOrSignUpRequest(BaseModel):
    email:str
    password:str


router = APIRouter()

@router.get("/me",tags=["auth"])
def me(user_id:str = Depends(get_current_user)):
    return{
        "user_id":user_id
    }

@router.post("/signUp",tags=["auth"])
def signUp(payload:LoginOrSignUpRequest):
    user_id = uuid.uuid4()
    new_user = Users(user_id=user_id,email=payload.email,pass_hash=hash_password(payload.password))

    try:
        with Session(engine) as session:
            session.add(new_user)
            session.commit()
            session.refresh(new_user)
            return (f"Created new user: {new_user}")

    except Exception as e:
        raise HTTPException(status_code=400,detail=f"error creating new user {e}")
    

@router.post("/login",tags=["auth"])
def login(payload:LoginOrSignUpRequest,response:Response):
    try:
        with Session(engine) as session:
            statement = select(Users).where(Users.email == payload.email)
            user = session.exec(statement).first()
            print(user)
            if not user:
                raise HTTPException(status_code=401, detail="Invalid email or password")
            
            if not verify_password(payload.password, user.pass_hash):
                raise HTTPException(status_code=401, detail="Invalid email or password")
            
            token_payload = {
                "sub":str(user.user_id),
                "email":user.email,
            }            
            token = create_token(token_payload)

            response.set_cookie(
                key="access_token",
                value=token,
                httponly=True,
                samesite="none",
                secure=True,
                max_age=10800
            )
            return {"message":"Login successful"}
        
    except HTTPException:
        raise
    
    except Exception as e:
        raise HTTPException(status_code=500,detail=f"error fetching user: {e}")
    

@router.post("/logout",tags=["auth"])
def logout(response:Response):
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="none",
        secure=True
    )
    return {
        "message":"Logged Out Successful"
    }
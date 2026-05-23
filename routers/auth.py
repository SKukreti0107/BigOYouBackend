import uuid
from fastapi import APIRouter, HTTPException, Response, Depends
from sqlmodel import Session, select, text

from helpers.auth.pass_hash import hash_password, verify_password
from helpers.auth.gen_JWT_token import create_token, decode_token
from helpers.auth.auth_deps import get_current_user
from modules.db import engine, Users, Interview_Session
from modules.schemas import LoginOrSignUpRequest, SignUpRequest, ProfileUpdateRequest, PasswordUpdateRequest

router = APIRouter()


@router.get("/me", tags=["auth"])
def me(user_id: str = Depends(get_current_user)):
    with Session(engine) as session:
        user = session.get(Users, uuid.UUID(user_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "user_id": str(user.user_id),
            "email": user.email,
            "username": user.username
        }


@router.post("/signUp", tags=["auth"])
def sign_up(payload: SignUpRequest):
    user_id = uuid.uuid4()
    new_user = Users(
        user_id=user_id,
        email=payload.email,
        pass_hash=hash_password(payload.password),
        username=payload.username
    )

    try:
        with Session(engine) as session:
            existing = session.exec(select(Users).where(Users.email == payload.email)).first()
            if existing:
                raise HTTPException(status_code=400, detail="Email is already in use")

            session.add(new_user)
            session.commit()
            session.refresh(new_user)
            return f"Created new user: {new_user.email}"

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"error creating new user {e}")


@router.post("/login", tags=["auth"])
def login(payload: LoginOrSignUpRequest, response: Response):
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
                "sub": str(user.user_id),
                "email": user.email,
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
            return {
                "message": "Login successful",
                "access_token": token
            }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"error fetching user: {e}")


@router.post("/logout", tags=["auth"])
def logout(response: Response):
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="none",
        secure=True
    )
    return {
        "message": "Logged Out Successful"
    }


@router.put("/user/profile", tags=["user"])
def update_profile(payload: ProfileUpdateRequest, user_id: str = Depends(get_current_user)):
    with Session(engine) as session:
        user_uuid = uuid.UUID(user_id)
        user = session.get(Users, user_uuid)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if email is being changed and is already taken
        if payload.email.lower() != user.email.lower():
            email_taken = session.exec(select(Users).where(Users.email == payload.email)).first()
            if email_taken:
                raise HTTPException(status_code=400, detail="Email address is already in use by another account.")

        user.email = payload.email
        user.username = payload.username
        session.add(user)
        session.commit()
        session.refresh(user)
        return {
            "message": "Profile updated successfully",
            "user": {
                "user_id": str(user.user_id),
                "email": user.email,
                "username": user.username
            }
        }


@router.put("/user/password", tags=["user"])
def update_password(payload: PasswordUpdateRequest, user_id: str = Depends(get_current_user)):
    with Session(engine) as session:
        user_uuid = uuid.UUID(user_id)
        user = session.get(Users, user_uuid)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if not verify_password(payload.current_password, user.pass_hash):
            raise HTTPException(status_code=400, detail="Incorrect current password")

        user.pass_hash = hash_password(payload.new_password)
        session.add(user)
        session.commit()
        return {"message": "Password updated successfully"}


@router.delete("/user/progress", tags=["user"])
def delete_progress(user_id: str = Depends(get_current_user)):
    with Session(engine) as session:
        user_uuid = uuid.UUID(user_id)

        # Get all interview sessions for the user
        sessions = session.exec(select(Interview_Session).where(Interview_Session.user_id == user_uuid)).all()
        session_ids = [s.session_id for s in sessions]

        if session_ids:
            ids_tuple = tuple(session_ids)
            session.exec(text("DELETE FROM session_feedback WHERE session_id IN :ids").bindparams(ids=ids_tuple))
            session.exec(text("DELETE FROM session_metrics WHERE session_id IN :ids").bindparams(ids=ids_tuple))
            session.exec(text("DELETE FROM session_message WHERE session_id IN :ids").bindparams(ids=ids_tuple))
            session.exec(text("DELETE FROM session_code_state WHERE session_id IN :ids").bindparams(ids=ids_tuple))

        # Delete interview sessions themselves
        session.exec(text("DELETE FROM interview_session WHERE user_id = :user_id").bindparams(user_id=user_uuid))
        # Delete user_problem_status
        session.exec(text("DELETE FROM user_problem_status WHERE user_id = :user_id").bindparams(user_id=user_uuid))

        session.commit()
        return {"message": "Progress reset successfully"}


@router.delete("/user/account", tags=["user"])
def delete_account(response: Response, user_id: str = Depends(get_current_user)):
    with Session(engine) as session:
        user_uuid = uuid.UUID(user_id)
        user = session.get(Users, user_uuid)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 1. Reset progress first
        sessions = session.exec(select(Interview_Session).where(Interview_Session.user_id == user_uuid)).all()
        session_ids = [s.session_id for s in sessions]

        if session_ids:
            ids_tuple = tuple(session_ids)
            session.exec(text("DELETE FROM session_feedback WHERE session_id IN :ids").bindparams(ids=ids_tuple))
            session.exec(text("DELETE FROM session_metrics WHERE session_id IN :ids").bindparams(ids=ids_tuple))
            session.exec(text("DELETE FROM session_message WHERE session_id IN :ids").bindparams(ids=ids_tuple))
            session.exec(text("DELETE FROM session_code_state WHERE session_id IN :ids").bindparams(ids=ids_tuple))

        session.exec(text("DELETE FROM interview_session WHERE user_id = :user_id").bindparams(user_id=user_uuid))
        session.exec(text("DELETE FROM user_problem_status WHERE user_id = :user_id").bindparams(user_id=user_uuid))

        # 2. Delete user
        session.delete(user)
        session.commit()

        # 3. Log out by deleting cookie
        response.delete_cookie(
            key="access_token",
            httponly=True,
            samesite="none",
            secure=True
        )
        return {"message": "Account and all data deleted successfully"}

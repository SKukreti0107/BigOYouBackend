from fastapi import Request,HTTPException,status
from helpers.auth.gen_JWT_token import decode_token

def get_current_user(request:Request):
    # 1. Try to extract token from the cookie
    token = request.cookies.get("access_token")

    # 2. Fallback: try to extract token from Authorization Bearer header
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    payload = decode_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    return user_id
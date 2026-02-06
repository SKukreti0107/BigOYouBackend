import jwt
from datetime import datetime, timedelta,timezone
from fastapi import HTTPException, status


secret_key = "4c71f75d-8e64-4a36-9950-d1fee7c46ef0"



def create_token(payload):
   payload['exp'] = datetime.now(timezone.utc) + timedelta(hours=3) 
   return jwt.encode(payload, secret_key, algorithm="HS256")



def decode_token(token):
   try:
       return jwt.decode(token, secret_key, algorithms=["HS256"])
   except jwt.ExpiredSignatureError:
       raise HTTPException(
           status_code=status.HTTP_401_UNAUTHORIZED,
           detail="Not authenticated"
       )
   except jwt.InvalidTokenError:
       raise HTTPException(
           status_code=status.HTTP_401_UNAUTHORIZED,
           detail="Not authenticated"
       )


if __name__  == '__main__':
    payload = {"user_id": 123, "username": "john_doe"}
    token = create_token(payload)
    print(f"Generated Token: {token}")
    decoded_payload = decode_token(token)
    print(f"Decoded Payload: {decoded_payload}")
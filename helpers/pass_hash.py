import bcrypt

def hash_password(plain_pass):
    if not plain_pass or not isinstance(plain_pass,str):
        raise ValueError("Pass must be non empty string")
    
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_pass.encode('utf-8'),salt)
    return hashed.decode('utf-8')


def verify_password(plain_pass,hash_pass):
    if isinstance(hash_pass,str):
        hash_pass = hash_pass.encode("utf-8")
    return bcrypt.checkpw(plain_pass.encode('utf-8'),hash_pass)
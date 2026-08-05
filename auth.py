import hashlib
import os
import time
import jwt
from typing import Optional

SECRET_KEY = os.getenv("JWT_SECRET", "libya_tech_secret_key_2026_super_secure")
ALGORITHM = "HS256"
TOKEN_EXPIRATION_SECONDS = 30 * 24 * 3600  # 30 Days

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ":" + key.hex()

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, key_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return secrets_compare(key, new_key)
    except Exception:
        return False

def secrets_compare(val1: bytes, val2: bytes) -> bool:
    return hashlib.sha256(val1).digest() == hashlib.sha256(val2).digest()

def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": int(time.time()) + TOKEN_EXPIRATION_SECONDS
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except Exception:
        return None

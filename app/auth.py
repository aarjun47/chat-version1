# ----------------------------------------------------
# app/auth.py
# Core auth engine — JWT creation/verification,
# password hashing, and route protection dependencies.
# ----------------------------------------------------

import os
from datetime import datetime, timezone, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET       = os.getenv("JWT_SECRET", "change_this_secret_in_production")
JWT_ALGORITHM    = "HS256"
JWT_EXPIRE_HOURS = 24

MASTER_USERNAME  = os.getenv("MASTER_USERNAME", "master")
MASTER_PASSWORD  = os.getenv("MASTER_PASSWORD", "changeme123")

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/client/login")


# =====================================================
# PASSWORD HELPERS
# =====================================================

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# =====================================================
# JWT HELPERS
# =====================================================

def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


# =====================================================
# DEPENDENCY: GET CURRENT USER FROM TOKEN
# Used by both master and client protected routes.
# =====================================================

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


# =====================================================
# DEPENDENCY: MASTER ONLY
# Attach to any route that only you should access.
# =====================================================

async def require_master(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "master":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master access required"
        )
    return user


# =====================================================
# DEPENDENCY: CLIENT ONLY
# Attach to any route a client institute accesses.
# client_id is extracted from the token — never
# trusted from URL params or request body.
# =====================================================

async def require_client(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "client":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client access required"
        )
    return user
# ----------------------------------------------------
# app/auth.py
# Core auth engine — JWT creation/verification,
# password hashing, and route protection dependencies.
# Uses bcrypt directly — no passlib dependency.
# ----------------------------------------------------

import os
import uuid
import bcrypt
from datetime import datetime, timezone, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv

from .database import blocklist_col

load_dotenv()

# =====================================================
# #3 FIX — Fail hard if secrets are missing
# Never allow defaults in production
# =====================================================

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable is not set")

MASTER_USERNAME = os.getenv("MASTER_USERNAME")
if not MASTER_USERNAME:
    raise RuntimeError("MASTER_USERNAME environment variable is not set")

MASTER_PASSWORD = os.getenv("MASTER_PASSWORD")
if not MASTER_PASSWORD:
    raise RuntimeError("MASTER_PASSWORD environment variable is not set")

JWT_ALGORITHM    = "HS256"
JWT_EXPIRE_HOURS = 24

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/client/login")


# =====================================================
# PASSWORD HELPERS
# =====================================================

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# =====================================================
# JWT HELPERS
# =====================================================

def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload["jti"] = str(uuid.uuid4())       # #4 FIX — unique token ID for revocation
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


# =====================================================
# #4 FIX — Revoke a token (call this on logout)
# Stores jti in blocklist until token naturally expires
# MongoDB TTL index auto-cleans expired entries
# =====================================================

async def revoke_token(token: str):
    payload = decode_token(token)
    if payload and payload.get("jti"):
        exp_timestamp = payload.get("exp")
        expires_at = (
            datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
            if exp_timestamp else None
        )
        await blocklist_col.insert_one({
            "jti": payload["jti"],
            "expires_at": expires_at
        })


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

    # #4 FIX — Check if token has been revoked
    jti = payload.get("jti")
    if jti:
        blocked = await blocklist_col.find_one({"jti": jti})
        if blocked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return payload


# =====================================================
# DEPENDENCY: MASTER ONLY
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
# =====================================================

async def require_client(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "client":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client access required"
        )
    return user
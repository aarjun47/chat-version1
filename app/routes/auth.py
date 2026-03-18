# ----------------------------------------------------
# routes/auth.py
# Login for both master and clients.
# Rate limited to prevent brute force attacks.
# ----------------------------------------------------

from fastapi import APIRouter, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from pydantic import BaseModel

from ..auth import (
    MASTER_USERNAME, MASTER_PASSWORD,
    verify_password, hash_password, create_token
)
from ..crud import get_user_by_username, update_user_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Rate limiter — keyed by IP address
limiter = Limiter(key_func=get_remote_address)


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# =====================================================
# MASTER LOGIN — 5 attempts per minute per IP
# =====================================================

@router.post("/master/login")
@limiter.limit("5/minute")
async def master_login(request: Request, body: LoginRequest):
    if body.username != MASTER_USERNAME or body.password != MASTER_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid master credentials"
        )
    token = create_token({"role": "master", "username": body.username})
    return {"access_token": token, "token_type": "bearer", "role": "master"}


# =====================================================
# CLIENT LOGIN — 10 attempts per minute per IP
# Slightly more lenient since clients may mistype
# =====================================================

@router.post("/client/login")
@limiter.limit("10/minute")
async def client_login(request: Request, body: LoginRequest):
    user = await get_user_by_username(body.username)

    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    token = create_token({
        "role": "client",
        "user_id": user["id"],
        "client_id": user["client_id"],
        "username": user["username"],
        "must_change_password": user.get("must_change_password", False)
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": "client",
        "client_id": user["client_id"],
        "must_change_password": user.get("must_change_password", False)
    }


# =====================================================
# CLIENT CHANGE PASSWORD — 5 attempts per minute
# =====================================================

@router.post("/client/change-password")
@limiter.limit("5/minute")
async def change_password(request: Request, body: ChangePasswordRequest):
    from ..auth import get_current_user, oauth2_scheme
    from fastapi import Depends

    # Auth is handled via the require_client dependency in client routes.
    # This endpoint is re-exposed here for the force-change flow.
    raise HTTPException(
        status_code=400,
        detail="Use /api/client/change-password with Authorization header"
    )
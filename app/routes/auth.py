# ----------------------------------------------------
# routes/auth.py
# Login for both master and clients.
# Rate limited to prevent brute force attacks.
# ----------------------------------------------------

from fastapi import APIRouter, HTTPException, Request, Response, Depends, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from pydantic import BaseModel

from ..auth import (
    MASTER_USERNAME, MASTER_PASSWORD,
    verify_password, hash_password, create_token,
    revoke_token, oauth2_scheme,
    CLIENT_AUTH_COOKIE, MASTER_AUTH_COOKIE,
)
from ..crud import get_user_by_username, update_user_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Rate limiter — keyed by IP address
limiter = Limiter(key_func=get_remote_address)


class LoginRequest(BaseModel):
    username: str
    password: str


def _cookie_options(request: Request) -> dict:
    host = (request.url.hostname or "").lower()
    is_local = host in {"localhost", "127.0.0.1"}

    return {
        "httponly": True,
        "secure": not is_local,
        "samesite": "lax" if is_local else "none",
        "max_age": 24 * 60 * 60,
        "path": "/",
    }


def _set_auth_cookie(response: Response, request: Request, cookie_name: str, token: str):
    response.set_cookie(cookie_name, token, **_cookie_options(request))


def _clear_auth_cookie(response: Response, request: Request, cookie_name: str):
    options = _cookie_options(request)
    response.delete_cookie(
        cookie_name,
        path=options["path"],
        secure=options["secure"],
        httponly=options["httponly"],
        samesite=options["samesite"],
    )


# =====================================================
# MASTER LOGIN — 5 attempts per minute per IP
# =====================================================

@router.post("/master/login")
@limiter.limit("5/minute")
async def master_login(request: Request, response: Response, body: LoginRequest):
    if body.username != MASTER_USERNAME or body.password != MASTER_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid master credentials"
        )
    token = create_token({"role": "master", "username": body.username})
    _set_auth_cookie(response, request, MASTER_AUTH_COOKIE, token)
    return {"role": "master", "username": body.username}


# =====================================================
# CLIENT LOGIN — 10 attempts per minute per IP
# Slightly more lenient since clients may mistype
# =====================================================

@router.post("/client/login")
@limiter.limit("10/minute")
async def client_login(request: Request, response: Response, body: LoginRequest):
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

    _set_auth_cookie(response, request, CLIENT_AUTH_COOKIE, token)

    return {
        "role": "client",
        "client_id": user["client_id"],
        "username": user["username"],
        "must_change_password": user.get("must_change_password", False)
    }


# =====================================================
# LOGOUT — revokes token so it cannot be reused
# even before natural 24hr expiry
# =====================================================

@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    bearer_token: str | None = Depends(oauth2_scheme),
):
    scope = (request.headers.get("x-auth-scope") or "").strip().lower()
    cookie_names = (
        [CLIENT_AUTH_COOKIE]
        if scope == "client"
        else [MASTER_AUTH_COOKIE]
        if scope == "master"
        else [CLIENT_AUTH_COOKIE, MASTER_AUTH_COOKIE]
    )

    tokens_to_revoke = set()
    if bearer_token:
        tokens_to_revoke.add(bearer_token)

    for cookie_name in cookie_names:
        cookie_token = request.cookies.get(cookie_name)
        if cookie_token:
            tokens_to_revoke.add(cookie_token)

    for token in tokens_to_revoke:
        await revoke_token(token)

    for cookie_name in cookie_names:
        _clear_auth_cookie(response, request, cookie_name)

    return {"status": "logged out"}

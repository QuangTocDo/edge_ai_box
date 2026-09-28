"""Lightweight session auth for the dashboard (demo-grade, not production).

Two roles ship by default:
  - admin  : full control (upload, process, start/stop cameras, delete)
  - viewer : read-only access to dashboards and evidence

Credentials default to admin/admin123 and user/user123, overridable via env
(ADMIN_PASSWORD / VIEWER_PASSWORD). Passwords are compared in constant time.
Tokens are random opaque strings kept in memory with a sliding expiry; restart
the server and everyone is logged out. This is intentionally simple — swap in a
real identity provider + hashed persistent users before any real deployment.
"""
from __future__ import annotations

import os
import secrets
import time
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel


TOKEN_TTL_SECONDS = 60 * 60 * 12  # 12 hours


# username -> profile. Passwords read from env with safe demo defaults.
USERS: Dict[str, Dict[str, str]] = {
    "admin": {
        "password": os.environ.get("ADMIN_PASSWORD", "admin123"),
        "role": "admin",
        "name": "Administrator",
    },
    "user": {
        "password": os.environ.get("VIEWER_PASSWORD", "user123"),
        "role": "viewer",
        "name": "Operator",
    },
}

# token -> {username, role, name, expires}
_SESSIONS: Dict[str, Dict[str, object]] = {}

_bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    username: str
    name: str
    role: str


class LoginResponse(UserInfo):
    token: str


def _issue_token(username: str) -> str:
    profile = USERS[username]
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = {
        "username": username,
        "role": profile["role"],
        "name": profile["name"],
        "expires": time.time() + TOKEN_TTL_SECONDS,
    }
    return token


def _resolve_session(token: Optional[str]) -> Optional[Dict[str, object]]:
    if not token:
        return None
    session = _SESSIONS.get(token)
    if session is None:
        return None
    if float(session["expires"]) < time.time():
        _SESSIONS.pop(token, None)
        return None
    return session


def current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> UserInfo:
    """FastAPI dependency: require a valid bearer token."""
    token = creds.credentials if creds else None
    session = _resolve_session(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return UserInfo(
        username=str(session["username"]),
        name=str(session["name"]),
        role=str(session["role"]),
    )


def require_admin(user: UserInfo = Depends(current_user)) -> UserInfo:
    """FastAPI dependency: require the admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    profile = USERS.get(payload.username)
    # Constant-time compare; still run a comparison for unknown users to avoid
    # leaking which usernames exist via timing.
    expected = profile["password"] if profile else secrets.token_hex(16)
    ok = secrets.compare_digest(payload.password, expected) and profile is not None
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = _issue_token(payload.username)
    return LoginResponse(
        token=token,
        username=payload.username,
        name=str(profile["name"]),
        role=str(profile["role"]),
    )


@router.get("/me", response_model=UserInfo)
def me(user: UserInfo = Depends(current_user)):
    return user


@router.post("/logout")
def logout(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)):
    if creds:
        _SESSIONS.pop(creds.credentials, None)
    return {"status": "ok"}

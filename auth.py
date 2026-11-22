"""
auth.py - API-key authentication with two roles.

  employee  can send requests (leave, policy questions) and see only their own
  reviewer  (HR) can also send requests, see every paused case, decide, and read the audit log

Tokens come from the environment, never from code:
    SYNAPSEHR_TOKENS="token1:E101:employee,token2:HR1:reviewer"
If it is not set, random demo tokens are created at start-up and printed once to the console.

Rules enforced in api.py on top of this:
  - the sender of a request is the signed-in user (the body cannot name someone else)
  - only reviewers can decide, and nobody can decide a case about themselves
  - employees cannot start resume screening (an HR function)
"""
import hmac
import os
import secrets
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

ROLES = ("employee", "reviewer")


@dataclass(frozen=True)
class User:
    user_id: str
    role: str


def load_users():
    """Return ({token: User}, generated) where generated is True when demo tokens were created."""
    raw = os.environ.get("SYNAPSEHR_TOKENS", "").strip()
    users, generated = {}, False
    if raw:
        for part in raw.split(","):
            token, user_id, role = (x.strip() for x in part.split(":"))
            if role not in ROLES:
                raise ValueError(f"unknown role {role!r} in SYNAPSEHR_TOKENS (use employee or reviewer)")
            if len(token) < 12:
                raise ValueError("tokens must be at least 12 characters")
            users[token] = User(user_id, role)
    else:
        generated = True
        for user_id, role in (("E101", "employee"), ("E102", "employee"), ("E103", "employee"), ("HR1", "reviewer"), ("HR2", "reviewer")):
            users[secrets.token_urlsafe(18)] = User(user_id, role)
    return users, generated


def find_user(users, token):
    for known, user in users.items():                   # constant-time comparison
        if hmac.compare_digest(known.encode(), (token or "").encode()):
            return user
    return None


def current_user(request: Request, x_api_key: str = Header(default="")):
    user = find_user(request.app.state.users, x_api_key)
    if user is None:
        raise HTTPException(401, "missing or invalid API key (send it in the X-API-Key header)")
    return user


def require_reviewer(request: Request, x_api_key: str = Header(default="")):
    user = current_user(request, x_api_key)
    if user.role != "reviewer":
        raise HTTPException(403, "this needs the reviewer role")
    return user

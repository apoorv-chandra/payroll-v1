"""FastAPI dependencies for auth + role checks."""
from __future__ import annotations

from fastapi import Request, HTTPException, Depends

from .security import decode_access_token
from .db import db


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one(
            {"_id": payload["sub"]}, {"password_hash": 0}
        )
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["id"] = user["_id"]
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_role(*roles: str):
    async def dep(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Forbidden: insufficient role")
        return user

    return dep


async def require_employer_or_admin(user: dict = Depends(get_current_user)):
    if user["role"] not in ("super_admin", "employer"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return user

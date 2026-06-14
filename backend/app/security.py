"""Auth primitives: passwords, tokens, captcha verification."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt

from .config import settings


# ---------- Password ----------
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------- JWT ----------
def create_access_token(user_id: str, role: str, employer_id: str | None) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "employer_id": employer_id,
        "exp": datetime.now(timezone.utc)
        + timedelta(hours=settings.JWT_EXPIRES_HOURS),
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


# ---------- Captcha ----------
def new_captcha_token() -> str:
    return secrets.token_urlsafe(18)


# ---------- File access tokens (signed download links) ----------
#
# Used by the Students module to embed clickable file URLs in Google Sheets
# cells without exposing GridFS ObjectIds as "secrets". A signed token binds
# the file id + tenant + expiry — without it, the file endpoint returns 401.
def sign_file_token(employer_id: str, file_id: str, ttl_days: int = 30) -> str:
    payload = {
        "employer_id": employer_id,
        "file_id": file_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=ttl_days),
        "type": "file",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_file_token(token: str) -> dict | None:
    try:
        data = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if data.get("type") != "file":
            return None
        return data
    except Exception:
        return None

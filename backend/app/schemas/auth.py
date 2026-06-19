"""Auth-related request/response schemas: login, signup, captcha."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class CaptchaIssue(BaseModel):
    """Server-issued captcha challenge (the answer never leaves the server)."""
    token: str
    a: int
    b: int
    op: str  # "+" or "-"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    captcha_token: Optional[str] = None
    captcha_answer: Optional[int] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class SignupRequest(BaseModel):
    """Public employee self-serve onboarding (SaaS distribution)."""
    signup_code: str = Field(min_length=6, max_length=16)
    name: str
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    phone: Optional[str] = None
    consent: bool = False
    captcha_token: Optional[str] = None
    captcha_answer: Optional[int] = None

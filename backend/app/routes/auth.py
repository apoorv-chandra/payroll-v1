"""Auth routes: login (with captcha), me, logout, captcha-issue."""
from __future__ import annotations

import random
from datetime import timedelta

from fastapi import APIRouter, Response, HTTPException, Depends

from ..db import db
from ..deps import get_current_user
from ..schemas import LoginRequest, TokenResponse, CaptchaIssue
from ..security import (
    create_access_token,
    new_captcha_token,
    verify_password,
)
from ..utils import gen_id, now_utc, public_user

router = APIRouter(prefix="/auth", tags=["auth"])

CAPTCHA_TTL_SECONDS = 5 * 60


@router.get("/captcha", response_model=CaptchaIssue)
async def issue_captcha():
    """Server-side maths captcha. The browser never sees the answer."""
    a = random.randint(2, 9)
    b = random.randint(1, 9)
    op = random.choice(["+", "-"])
    answer = a + b if op == "+" else a - b
    token = new_captcha_token()
    await db.captchas.insert_one({
        "_id": gen_id(),
        "token": token,
        "answer": answer,
        "expires_at": now_utc() + timedelta(seconds=CAPTCHA_TTL_SECONDS),
        "consumed": False,
    })
    return CaptchaIssue(token=token, a=a, b=b, op=op)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, response: Response):
    if not (payload.captcha_token and payload.captcha_answer is not None):
        raise HTTPException(status_code=400, detail="Captcha required")
    cap = await db.captchas.find_one({"token": payload.captcha_token})
    if not cap or cap.get("consumed") or cap["expires_at"].replace(tzinfo=None) < now_utc().replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="Captcha expired — please refresh")
    if int(payload.captcha_answer) != int(cap["answer"]):
        await db.captchas.update_one({"_id": cap["_id"]}, {"$set": {"consumed": True}})
        raise HTTPException(status_code=400, detail="Captcha incorrect")
    await db.captchas.update_one({"_id": cap["_id"]}, {"$set": {"consumed": True}})

    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.get("disabled"):
        raise HTTPException(status_code=403, detail="Account disabled")
    token = create_access_token(user["_id"], user["role"], user.get("tenant_id"))
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=43200,
        path="/",
    )
    return TokenResponse(access_token=token, user=public_user(user))


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)

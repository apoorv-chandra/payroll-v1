"""Auth routes: login (with captcha), me, logout, captcha-issue, public signup."""
from __future__ import annotations

import random
from datetime import timedelta

from fastapi import APIRouter, Response, HTTPException, Depends

from ..db import db
from ..deps import get_current_user
from ..schemas import (
    LoginRequest,
    TokenResponse,
    CaptchaIssue,
    SignupRequest,
    EmployerPublic,
)
from ..security import (
    create_access_token,
    hash_password,
    new_captcha_token,
    verify_password,
)
from ..utils import gen_id, now_utc, public_user, today_iso

router = APIRouter(prefix="/auth", tags=["auth"])

CAPTCHA_TTL_SECONDS = 5 * 60


async def _consume_captcha(token: str | None, answer: int | None) -> None:
    if not (token and answer is not None):
        raise HTTPException(status_code=400, detail="Captcha required")
    cap = await db.captchas.find_one({"token": token})
    if not cap or cap.get("consumed") or cap["expires_at"].replace(tzinfo=None) < now_utc().replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="Captcha expired — please refresh")
    if int(answer) != int(cap["answer"]):
        await db.captchas.update_one({"_id": cap["_id"]}, {"$set": {"consumed": True}})
        raise HTTPException(status_code=400, detail="Captcha incorrect")
    await db.captchas.update_one({"_id": cap["_id"]}, {"$set": {"consumed": True}})


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
    await _consume_captcha(payload.captcha_token, payload.captcha_answer)

    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.get("disabled"):
        raise HTTPException(
            status_code=403,
            detail="Your account is awaiting employer approval. We'll email you once it's activated.",
        )
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


# ---------- Public employee self-serve onboarding (SaaS distribution) ----------
@router.get("/employers", response_model=list[EmployerPublic])
async def public_employers():
    """Public list of employer workspaces a new employee can request to join."""
    out: list[EmployerPublic] = []
    async for t in db.tenants.find({}).sort("name", 1):
        out.append(EmployerPublic(id=t["_id"], name=t.get("name") or "—"))
    return out


@router.post("/signup")
async def signup(payload: SignupRequest):
    """Public route — creates a 'pending_approval' employee under the chosen tenant.

    The user account is created with `disabled=True`, so login is blocked
    until the employer approves the request from their dashboard.
    """
    if not payload.consent:
        raise HTTPException(
            status_code=400,
            detail="You must accept the Privacy Notice (DPDP) to continue.",
        )
    await _consume_captcha(payload.captcha_token, payload.captcha_answer)

    tenant = await db.tenants.find_one({"_id": payload.tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Selected employer not found")

    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(
            status_code=400,
            detail="This email is already registered. Try signing in instead.",
        )

    # Auto-generate a placeholder employee code; employer can rename on approval.
    placeholder_code = f"NEW-{gen_id()[:6].upper()}"
    emp_id = gen_id()
    user_id = gen_id()
    ts = now_utc()

    await db.users.insert_one({
        "_id": user_id,
        "email": email,
        "password_hash": hash_password(payload.password),
        "name": payload.name.strip(),
        "role": "employee",
        "tenant_id": tenant["_id"],
        "employee_id": emp_id,
        "elevated_roles": [],
        "phone": payload.phone,
        "disabled": True,                    # ← blocks login until approval
        "created_at": ts,
    })
    await db.employees.insert_one({
        "_id": emp_id,
        "tenant_id": tenant["_id"],
        "user_id": user_id,
        "emp_code": placeholder_code,
        "name": payload.name.strip(),
        "email": email,
        "phone": payload.phone,
        "designation": None,
        "department": None,
        "monthly_salary": 0.0,                # employer fills on approval
        "joining_date": today_iso(),
        "bank_account": None,
        "ifsc": None,
        "elevated_roles": [],
        "attendance_config_id": 1,
        "active": False,                     # ← inactive until approval
        "signup_status": "pending",          # pending | approved | rejected
        "self_signup": True,
        "consent_given_at": ts,
        "created_at": ts,
    })
    return {
        "ok": True,
        "tenant_name": tenant.get("name"),
        "message": "Your request has been forwarded to your employer. You'll be able to sign in once they approve it.",
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)

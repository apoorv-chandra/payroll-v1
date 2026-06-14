"""Auth routes: login (with captcha), me, logout, captcha-issue, public signup."""
from __future__ import annotations

import random
from datetime import timedelta

from fastapi import APIRouter, Response, HTTPException, Depends

from ..db import db, employer_db
from ..deps import get_current_user
from ..schemas import (
    LoginRequest,
    TokenResponse,
    CaptchaIssue,
    SignupRequest,
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
    token = create_access_token(user["_id"], user["role"], user.get("employer_id"))
    # Wipe the initial password on first successful login — from that point
    # forward the employer no longer needs (or sees) it.
    if user.get("initial_password_plain"):
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$unset": {"initial_password_plain": ""}, "$set": {"first_login_at": now_utc()}},
        )
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
@router.post("/signup")
async def signup(payload: SignupRequest):
    """Public route — creates a 'pending_approval' employee using an employer
    invite code. The employer issues this 8-char code from their Settings page;
    sharing it is what gates access to the platform (no public list of clients).

    The user account is created with `disabled=True`, so login is blocked
    until the employer approves the request from their dashboard.
    """
    if not payload.consent:
        raise HTTPException(
            status_code=400,
            detail="You must accept the Privacy Notice (DPDP) to continue.",
        )
    await _consume_captcha(payload.captcha_token, payload.captcha_answer)

    code = (payload.signup_code or "").upper().replace(" ", "").replace("-", "").strip()
    if len(code) < 6:
        raise HTTPException(status_code=400, detail="Invite code looks too short.")
    tenant = await db.employers.find_one({"signup_code": code, "active": True})
    if not tenant:
        raise HTTPException(status_code=404, detail="Invite code not recognised. Please check with your employer.")

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
        # Self-signup: never store plaintext — the user already knows their own
        # password and the employer hasn't issued it. They'll change it in
        # Settings if they wish.
        "name": payload.name.strip(),
        "role": "employee",
        "employer_id": tenant["_id"],
        "employee_id": emp_id,
        "elevated_roles": [],
        "phone": payload.phone,
        "disabled": True,                    # ← blocks login until approval
        "created_at": ts,
    })
    await employer_db(tenant["_id"]).employees.insert_one({
        "_id": emp_id,
        "employer_id": tenant["_id"],
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


# ---------- Password management ----------

@router.post("/change-password")
async def change_password(payload: dict, user: dict = Depends(get_current_user)):
    """Authenticated user changes their own password.
    Validates the current password to prevent session-hijack abuse."""
    current = (payload or {}).get("current_password") or ""
    new = (payload or {}).get("new_password") or ""
    if len(new) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")
    # get_current_user strips password_hash; refetch full user record.
    full = await db.users.find_one({"_id": user["_id"]})
    if not full:
        raise HTTPException(status_code=401, detail="User not found")
    if not verify_password(current, full["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if verify_password(new, full["password_hash"]):
        raise HTTPException(status_code=400, detail="New password must differ from the current one.")
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"password_hash": hash_password(new), "password_changed_at": now_utc()},
            "$unset": {"initial_password_plain": ""},
        },
    )
    return {"ok": True}


@router.post("/forgot-password")
async def forgot_password(payload: dict):
    """Self-service password reset for employees who forgot their password.

    Flow: employee enters email + new password → backend marks the request
    'pending' → employer sees it in their dashboard → employer approves →
    new password takes effect. This avoids the employer ever seeing the
    plaintext password.
    """
    email = ((payload or {}).get("email") or "").lower().strip()
    new = (payload or {}).get("new_password") or ""
    if len(new) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")
    user = await db.users.find_one({"email": email})
    # Never reveal whether the email exists; return ok either way.
    if user and user["role"] == "employee":
        tdb = employer_db(user["employer_id"])
        # Replace any earlier pending request for the same user.
        await tdb.password_reset_requests.delete_many({"user_id": user["_id"], "status": "pending"})
        await tdb.password_reset_requests.insert_one({
            "_id": gen_id(),
            "employer_id": user["employer_id"],
            "user_id": user["_id"],
            "email": email,
            "name": user.get("name"),
            "new_password_hash": hash_password(new),   # hashed, never stored plaintext
            "status": "pending",
            "created_at": now_utc(),
        })
    return {
        "ok": True,
        "message": "If that email is registered, your employer has been notified. They'll approve your new password shortly.",
    }


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)

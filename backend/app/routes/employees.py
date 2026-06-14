"""Tenant settings + employee CRUD."""
from __future__ import annotations

import asyncio
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from ..db import db, tenant_db
from ..deps import get_current_user, require_employer_or_admin, require_role
from ..schemas import (
    CreateEmployeeRequest,
    UpdateEmployeeRequest,
    TenantSettingsUpdate,
    ApproveSignupRequest,
)
from ..security import hash_password
from ..services.audit import audit
from ..services.email import (
    send_email,
    render_email,
    render_welcome_body,
)
from ..services.seed import default_leave_types
from ..utils import gen_id, now_utc, today_iso, strip_id

router = APIRouter(tags=["tenant+employees"])


# ---------- helpers ----------
async def get_tenant(tenant_id: str) -> dict:
    t = await db.tenants.find_one({"_id": tenant_id})
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    # `_id` is a UUID string. Re-pack into a plain dict to keep type-hints honest.
    return dict(t)


async def reset_leave_balances(tenant_id: str, employee_id: str, joining_date: str | None = None):
    tdb = tenant_db(tenant_id)
    t = await get_tenant(tenant_id)
    leave_types = t.get("settings", {}).get("leave_types", default_leave_types())
    today = date.today()
    reset_month = t.get("settings", {}).get("leave_reset_month", 4)
    fiscal_start = date(
        today.year if today.month >= reset_month else today.year - 1, reset_month, 1
    )
    join = None
    if joining_date:
        try:
            join = date.fromisoformat(joining_date)
        except Exception:
            join = None
    months_remaining = 12
    if join and join > fiscal_start:
        months_remaining = max(
            1,
            12 - ((join.year - fiscal_start.year) * 12 + (join.month - fiscal_start.month)),
        )
    for lt in leave_types:
        prorated = round((lt["annual_quota"] * months_remaining) / 12.0, 2)
        await tdb.leave_balances.update_one(
            {"tenant_id": tenant_id, "employee_id": employee_id, "leave_type": lt["code"]},
            {"$set": {
                "tenant_id": tenant_id,
                "employee_id": employee_id,
                "leave_type": lt["code"],
                "quota": prorated,
                "used": 0,
                "fiscal_start": fiscal_start.isoformat(),
            },
             "$setOnInsert": {"_id": gen_id(), "pending": 0}},
            upsert=True,
        )


# ---------- Tenant settings ----------
@router.get("/tenant/settings")
async def get_settings(user: dict = Depends(require_employer_or_admin)):
    if user["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Super admin has no tenant")
    t = await get_tenant(user["tenant_id"])
    return {
        "id": t["_id"],
        "name": t["name"],
        "signup_code": t.get("signup_code"),
        "settings": t.get("settings", {}),
        "address": t.get("address"),
        "phone": t.get("phone"),
    }


@router.put("/tenant/settings")
async def update_settings(req: TenantSettingsUpdate, user: dict = Depends(require_role("employer"))):
    upd: dict = {}
    if req.leave_types is not None:
        upd["settings.leave_types"] = [lt.model_dump() for lt in req.leave_types]
    if req.leave_reset_month is not None:
        upd["settings.leave_reset_month"] = req.leave_reset_month
    if req.attendance is not None:
        upd["settings.attendance"] = req.attendance.model_dump()
    if req.company_logo_url is not None:
        upd["settings.company_logo_url"] = req.company_logo_url
    if upd:
        await db.tenants.update_one({"_id": user["tenant_id"]}, {"$set": upd})
    await audit(user["tenant_id"], user["_id"], "tenant.settings.update", user["tenant_id"], upd)
    t = await get_tenant(user["tenant_id"])
    return t.get("settings", {})


# ---------- Employees ----------
@router.post("/employees")
async def create_employee(
    req: CreateEmployeeRequest, user: dict = Depends(require_role("employer"))
):
    tdb = tenant_db(user["tenant_id"])
    email = req.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already in use")
    if await tdb.employees.find_one({"tenant_id": user["tenant_id"], "emp_code": req.emp_code}):
        raise HTTPException(status_code=400, detail="Employee code already exists")
    emp_id = gen_id()
    user_id = gen_id()
    # Inherit employer's enabled features by default. Employer can later
    # narrow this via PUT /api/employees/{user_id}/features.
    tenant = await db.tenants.find_one({"_id": user["tenant_id"]}, {"enabled_features": 1})
    employer_enabled = list((tenant or {}).get("enabled_features") or ["payroll"])
    await db.users.insert_one({
        "_id": user_id,
        "email": email,
        "password_hash": hash_password(req.password),
        "initial_password_plain": req.password,  # cleared on first login
        "name": req.name,
        "role": "employee",
        "tenant_id": user["tenant_id"],
        "employee_id": emp_id,
        "elevated_roles": req.elevated_roles or [],
        "phone": req.phone,
        "feature_permissions": employer_enabled,
        "created_at": now_utc(),
    })
    await tdb.employees.insert_one({
        "_id": emp_id,
        "tenant_id": user["tenant_id"],
        "user_id": user_id,
        "emp_code": req.emp_code,
        "name": req.name,
        "email": email,
        "phone": req.phone,
        "designation": req.designation,
        "department": req.department,
        "monthly_salary": req.monthly_salary,
        "joining_date": req.joining_date or today_iso(),
        "bank_account": req.bank_account,
        "ifsc": req.ifsc,
        "elevated_roles": req.elevated_roles or [],
        "attendance_config_id": req.attendance_config_id,
        "active": True,
        "created_at": now_utc(),
    })
    await reset_leave_balances(user["tenant_id"], emp_id, req.joining_date)
    await audit(user["tenant_id"], user["_id"], "employee.create", emp_id, {"name": req.name})

    # ✅ Welcome email is the only event still wired to email.
    tenant_doc = await db.tenants.find_one({"_id": user["tenant_id"]})
    company = (tenant_doc or {}).get("name", "Payroll")
    body = render_welcome_body(req.name, company, email, req.password, req.emp_code)
    asyncio.create_task(send_email(
        email,
        f"Welcome to {company} — your Payroll login",
        render_email("WELCOME", body),
    ))
    return {"id": emp_id, "user_id": user_id}


@router.get("/employees")
async def list_employees(user: dict = Depends(require_employer_or_admin)):
    tdb = tenant_db(user["tenant_id"])
    if user["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Use tenant scope")
    # Bulk-fetch the linked user docs once so we can attach feature_permissions
    # without an N+1 query per row.
    user_ids = []
    employees = []
    async for e in tdb.employees.find({"tenant_id": user["tenant_id"]}).sort("emp_code", 1):
        if e.get("signup_status") == "pending":
            continue
        employees.append(e)
        if e.get("user_id"):
            user_ids.append(e["user_id"])
    perms_by_uid: dict[str, list[str]] = {}
    if user_ids:
        async for u in db.users.find(
            {"_id": {"$in": user_ids}}, {"feature_permissions": 1}
        ):
            perms_by_uid[u["_id"]] = list(u.get("feature_permissions") or [])
    out = []
    for e in employees:
        row = strip_id(e)
        row["feature_permissions"] = perms_by_uid.get(e.get("user_id"), [])
        out.append(row)
    return out


# ---------- Pending self-signups (Employer approval workflow) ----------
@router.get("/employees/pending")
async def list_pending_signups(user: dict = Depends(require_role("employer"))):
    tdb = tenant_db(user["tenant_id"])
    out = []
    async for e in (
        tdb.employees.find({"tenant_id": user["tenant_id"], "signup_status": "pending"})
        .sort("created_at", -1)
    ):
        out.append(strip_id(e))
    return out


@router.post("/employees/{employee_id}/approve")
async def approve_signup(
    employee_id: str,
    req: ApproveSignupRequest = ApproveSignupRequest(),
    user: dict = Depends(require_role("employer")),
):
    """Approve a pending signup — fills in the employer-managed fields
    (emp_code, salary, designation, etc.) and activates the account."""
    tdb = tenant_db(user["tenant_id"])
    e = await tdb.employees.find_one({
        "_id": employee_id,
        "tenant_id": user["tenant_id"],
        "signup_status": "pending",
    })
    if not e:
        raise HTTPException(status_code=404, detail="Pending signup not found")

    # Validate emp_code uniqueness within tenant.
    if req.emp_code:
        clash = await tdb.employees.find_one({
            "tenant_id": user["tenant_id"],
            "emp_code": req.emp_code,
            "_id": {"$ne": employee_id},
        })
        if clash:
            raise HTTPException(status_code=400, detail="Employee code already exists")

    upd = {
        "active": True,
        "signup_status": "approved",
        "approved_at": now_utc(),
        "approved_by": user["_id"],
    }
    for k in ("emp_code", "designation", "department", "bank_account", "ifsc",
             "attendance_config_id", "joining_date"):
        v = getattr(req, k, None)
        if v is not None:
            upd[k] = v
    if req.monthly_salary is not None:
        upd["monthly_salary"] = float(req.monthly_salary)
    if req.elevated_roles is not None:
        upd["elevated_roles"] = req.elevated_roles

    await tdb.employees.update_one({"_id": employee_id}, {"$set": upd})
    user_upd = {"disabled": False}
    if req.elevated_roles is not None:
        user_upd["elevated_roles"] = req.elevated_roles
    # Grant the approved signup the same modules the employer currently has.
    tenant_doc_for_features = await db.tenants.find_one(
        {"_id": user["tenant_id"]}, {"enabled_features": 1}
    )
    user_upd["feature_permissions"] = list(
        (tenant_doc_for_features or {}).get("enabled_features") or ["payroll"]
    )
    await db.users.update_one({"_id": e["user_id"]}, {"$set": user_upd})

    await reset_leave_balances(
        user["tenant_id"],
        employee_id,
        upd.get("joining_date") or e.get("joining_date"),
    )
    await audit(user["tenant_id"], user["_id"], "employee.signup.approve", employee_id, upd)

    # Welcome email — same template, but tells them the account is now active.
    tenant_doc = await db.tenants.find_one({"_id": user["tenant_id"]})
    company = (tenant_doc or {}).get("name", "Payroll")
    body = render_welcome_body(
        e.get("name") or "there",
        company,
        e.get("email"),
        "(use the password you chose at signup)",
        upd.get("emp_code") or e.get("emp_code"),
    )
    asyncio.create_task(send_email(
        e.get("email"),
        f"Welcome to {company} — your account is now active",
        render_email("WELCOME", body),
    ))
    return {"ok": True, "id": employee_id}


@router.post("/employees/{employee_id}/reject")
async def reject_signup(
    employee_id: str,
    user: dict = Depends(require_role("employer")),
):
    """Reject a pending signup — purges the employee + user record entirely."""
    tdb = tenant_db(user["tenant_id"])
    e = await tdb.employees.find_one({
        "_id": employee_id,
        "tenant_id": user["tenant_id"],
        "signup_status": "pending",
    })
    if not e:
        raise HTTPException(status_code=404, detail="Pending signup not found")
    await tdb.employees.delete_one({"_id": employee_id})
    await db.users.delete_one({"_id": e["user_id"]})
    await audit(
        user["tenant_id"], user["_id"], "employee.signup.reject", employee_id,
        {"email": e.get("email"), "name": e.get("name")},
    )
    return {"ok": True}


@router.get("/employees/{employee_id}")
async def get_employee(employee_id: str, user: dict = Depends(get_current_user)):
    tdb = tenant_db(user["tenant_id"])
    e = await tdb.employees.find_one({"_id": employee_id})
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] != "super_admin" and e["tenant_id"] != user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return strip_id(e)


@router.put("/employees/{employee_id}")
async def update_employee(
    employee_id: str,
    req: UpdateEmployeeRequest,
    user: dict = Depends(require_role("employer")),
):
    tdb = tenant_db(user["tenant_id"])
    e = await tdb.employees.find_one({"_id": employee_id, "tenant_id": user["tenant_id"]})
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    upd = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
    if upd:
        await tdb.employees.update_one({"_id": employee_id}, {"$set": upd})
        if "name" in upd or "elevated_roles" in upd or "phone" in upd:
            user_upd = {}
            if "name" in upd:
                user_upd["name"] = upd["name"]
            if "elevated_roles" in upd:
                user_upd["elevated_roles"] = upd["elevated_roles"]
            if "phone" in upd:
                user_upd["phone"] = upd["phone"]
            if user_upd:
                await db.users.update_one({"_id": e["user_id"]}, {"$set": user_upd})
    await audit(user["tenant_id"], user["_id"], "employee.update", employee_id, upd)
    return {"ok": True}


@router.delete("/employees/{employee_id}")
async def delete_employee(
    employee_id: str, user: dict = Depends(require_role("employer"))
):
    tdb = tenant_db(user["tenant_id"])
    e = await tdb.employees.find_one({"_id": employee_id, "tenant_id": user["tenant_id"]})
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    await tdb.employees.delete_one({"_id": employee_id})
    await db.users.delete_one({"_id": e["user_id"]})
    await tdb.attendance.delete_many({"employee_id": employee_id})
    await tdb.leave_applications.delete_many({"employee_id": employee_id})
    await tdb.leave_balances.delete_many({"employee_id": employee_id})
    await audit(user["tenant_id"], user["_id"], "employee.delete", employee_id)
    return {"ok": True}



# ---------- Employee credentials & password reset (employer-only) ----------

def _temp_password() -> str:
    """8-char readable password — letters + digits, no ambiguous chars."""
    from ..utils import _SIGNUP_CODE_ALPHABET
    import secrets
    return "".join(secrets.choice(_SIGNUP_CODE_ALPHABET) for _ in range(8))


@router.get("/employees/{employee_id}/credentials")
async def employee_credentials(
    employee_id: str,
    user: dict = Depends(require_role("employer")),
):
    """Returns the employee's email + initial password if they HAVEN'T logged in
    yet. After first login the initial password is auto-wiped from the DB and
    only a fresh 'Reset password' will create a new one to share."""
    tdb = tenant_db(user["tenant_id"])
    e = await tdb.employees.find_one({"_id": employee_id, "tenant_id": user["tenant_id"]})
    if not e:
        raise HTTPException(status_code=404, detail="Employee not found")
    u = await db.users.find_one({"_id": e["user_id"]}) or {}
    return {
        "email": u.get("email"),
        "initial_password": u.get("initial_password_plain"),
        "first_login_at": u.get("first_login_at"),
        "password_changed_at": u.get("password_changed_at"),
    }


@router.post("/employees/{employee_id}/reset-password")
async def reset_employee_password(
    employee_id: str,
    user: dict = Depends(require_role("employer")),
):
    """Generates a new temporary password for an employee and stores it
    visible (plaintext) ONLY until that employee next logs in."""
    tdb = tenant_db(user["tenant_id"])
    e = await tdb.employees.find_one({"_id": employee_id, "tenant_id": user["tenant_id"]})
    if not e:
        raise HTTPException(status_code=404, detail="Employee not found")
    pw = _temp_password()
    await db.users.update_one(
        {"_id": e["user_id"]},
        {
            "$set": {
                "password_hash": hash_password(pw),
                "initial_password_plain": pw,
                "password_reset_at": now_utc(),
            },
            "$unset": {"first_login_at": "", "password_changed_at": ""},
        },
    )
    await audit(user["tenant_id"], user["_id"], "employee.password.reset", employee_id)
    return {"ok": True, "initial_password": pw}


# ---------- Self-service password-reset requests (employer approval queue) ----------

@router.get("/employees/password-reset/pending")
async def list_pending_password_resets(user: dict = Depends(require_role("employer"))):
    tdb = tenant_db(user["tenant_id"])
    out = []
    async for r in tdb.password_reset_requests.find({"status": "pending"}).sort("created_at", -1):
        r["id"] = r["_id"]
        # Never expose the hash.
        out.append({k: v for k, v in r.items() if k not in ("_id", "new_password_hash")})
    return out


@router.post("/employees/password-reset/{req_id}/approve")
async def approve_password_reset(
    req_id: str,
    user: dict = Depends(require_role("employer")),
):
    tdb = tenant_db(user["tenant_id"])
    rec = await tdb.password_reset_requests.find_one({"_id": req_id, "status": "pending"})
    if not rec:
        raise HTTPException(status_code=404, detail="Request not found")
    await db.users.update_one(
        {"_id": rec["user_id"]},
        {
            "$set": {"password_hash": rec["new_password_hash"], "password_reset_at": now_utc()},
            "$unset": {"initial_password_plain": ""},
        },
    )
    await tdb.password_reset_requests.update_one(
        {"_id": req_id},
        {"$set": {"status": "approved", "approved_at": now_utc(), "approved_by": user["_id"]}},
    )
    await audit(user["tenant_id"], user["_id"], "employee.password.reset_approved", rec["user_id"])
    return {"ok": True}


@router.post("/employees/password-reset/{req_id}/reject")
async def reject_password_reset(
    req_id: str,
    user: dict = Depends(require_role("employer")),
):
    tdb = tenant_db(user["tenant_id"])
    res = await tdb.password_reset_requests.update_one(
        {"_id": req_id, "status": "pending"},
        {"$set": {"status": "rejected", "rejected_at": now_utc(), "rejected_by": user["_id"]}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"ok": True}

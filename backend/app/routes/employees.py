"""Tenant settings + employee CRUD."""
from __future__ import annotations

import asyncio
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from ..db import db
from ..deps import get_current_user, require_employer_or_admin, require_role
from ..schemas import (
    CreateEmployeeRequest,
    UpdateEmployeeRequest,
    TenantSettingsUpdate,
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
    return t


async def reset_leave_balances(tenant_id: str, employee_id: str, joining_date: str | None = None):
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
        await db.leave_balances.update_one(
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
    email = req.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already in use")
    if await db.employees.find_one({"tenant_id": user["tenant_id"], "emp_code": req.emp_code}):
        raise HTTPException(status_code=400, detail="Employee code already exists")
    emp_id = gen_id()
    user_id = gen_id()
    await db.users.insert_one({
        "_id": user_id,
        "email": email,
        "password_hash": hash_password(req.password),
        "name": req.name,
        "role": "employee",
        "tenant_id": user["tenant_id"],
        "employee_id": emp_id,
        "elevated_roles": req.elevated_roles or [],
        "phone": req.phone,
        "created_at": now_utc(),
    })
    await db.employees.insert_one({
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
    if user["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Use tenant scope")
    out = []
    async for e in db.employees.find({"tenant_id": user["tenant_id"]}).sort("emp_code", 1):
        out.append(strip_id(e))
    return out


@router.get("/employees/{employee_id}")
async def get_employee(employee_id: str, user: dict = Depends(get_current_user)):
    e = await db.employees.find_one({"_id": employee_id})
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
    e = await db.employees.find_one({"_id": employee_id, "tenant_id": user["tenant_id"]})
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    upd = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
    if upd:
        await db.employees.update_one({"_id": employee_id}, {"$set": upd})
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
    e = await db.employees.find_one({"_id": employee_id, "tenant_id": user["tenant_id"]})
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    await db.employees.delete_one({"_id": employee_id})
    await db.users.delete_one({"_id": e["user_id"]})
    await db.attendance.delete_many({"employee_id": employee_id})
    await db.leave_applications.delete_many({"employee_id": employee_id})
    await db.leave_balances.delete_many({"employee_id": employee_id})
    await audit(user["tenant_id"], user["_id"], "employee.delete", employee_id)
    return {"ok": True}

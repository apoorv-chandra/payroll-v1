"""Super-admin routes: tenants (employers), audit, stats, platform settings."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db import db
from ..deps import require_role
from ..schemas import CreateEmployerRequest, PlatformSettingsUpdate
from ..security import hash_password
from ..services.audit import audit
from ..services.seed import default_leave_types
from ..utils import gen_id, now_utc, public_user, today_iso

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/employers")
async def create_employer(
    req: CreateEmployerRequest, user: dict = Depends(require_role("super_admin"))
):
    admin_email = req.admin_email.lower().strip()
    if await db.users.find_one({"email": admin_email}):
        raise HTTPException(status_code=400, detail="Email already in use")
    tenant_id = gen_id()
    await db.tenants.insert_one({
        "_id": tenant_id,
        "name": req.name,
        "address": req.address,
        "phone": req.phone,
        "created_at": now_utc(),
        "active": True,
        "settings": {
            "leave_reset_month": 4,
            "leave_types": default_leave_types(),
            "attendance": {
                "default_config_id": 1,
                "geo_fence": {"enabled": False},
                "working_days_per_month": 26,
            },
            "company_logo_url": None,
        },
    })
    employer_user_id = gen_id()
    await db.users.insert_one({
        "_id": employer_user_id,
        "email": admin_email,
        "password_hash": hash_password(req.admin_password),
        "name": req.admin_name,
        "role": "employer",
        "tenant_id": tenant_id,
        "created_at": now_utc(),
    })
    await audit(tenant_id, user["_id"], "tenant.create", tenant_id, {"name": req.name})
    return {"id": tenant_id, "admin_user_id": employer_user_id}


@router.get("/employers")
async def list_employers(user: dict = Depends(require_role("super_admin"))):
    out = []
    async for t in db.tenants.find({}, {}).sort("created_at", -1):
        admin = await db.users.find_one(
            {"tenant_id": t["_id"], "role": "employer"}, {"password_hash": 0}
        )
        emp_count = await db.employees.count_documents({"tenant_id": t["_id"]})
        t["id"] = t["_id"]
        t["admin"] = public_user(admin)
        t["employee_count"] = emp_count
        out.append({k: v for k, v in t.items() if k != "_id"})
    return out


@router.delete("/employers/{tenant_id}")
async def delete_employer(tenant_id: str, user: dict = Depends(require_role("super_admin"))):
    await db.tenants.delete_one({"_id": tenant_id})
    await db.users.delete_many({"tenant_id": tenant_id})
    await db.employees.delete_many({"tenant_id": tenant_id})
    await db.attendance.delete_many({"tenant_id": tenant_id})
    await db.leave_applications.delete_many({"tenant_id": tenant_id})
    await db.leave_balances.delete_many({"tenant_id": tenant_id})
    await db.payroll_runs.delete_many({"tenant_id": tenant_id})
    await db.payroll_items.delete_many({"tenant_id": tenant_id})
    await audit(None, user["_id"], "tenant.delete", tenant_id)
    return {"ok": True}


@router.get("/audit")
async def list_audit(user: dict = Depends(require_role("super_admin")), limit: int = 100):
    items = []
    async for a in db.audit_logs.find().sort("created_at", -1).limit(limit):
        a["id"] = a["_id"]
        items.append({k: v for k, v in a.items() if k != "_id"})
    return items


@router.get("/stats")
async def admin_stats(user: dict = Depends(require_role("super_admin"))):
    return {
        "tenants": await db.tenants.count_documents({}),
        "employees": await db.employees.count_documents({}),
        "attendance_today": await db.attendance.count_documents({"date": today_iso()}),
        "active_payrolls": await db.payroll_runs.count_documents(
            {"status": {"$in": ["draft", "pending_approval", "approved"]}}
        ),
    }


# ---------- Platform settings (feature flags) ----------
@router.get("/platform-settings")
async def get_platform_settings(user: dict = Depends(require_role("super_admin"))):
    out: dict = {}
    async for s in db.platform_settings.find({}):
        out[s["key"]] = s.get("value")
    return out


@router.put("/platform-settings")
async def update_platform_settings(
    req: PlatformSettingsUpdate,
    user: dict = Depends(require_role("super_admin")),
):
    payload = req.model_dump(exclude_unset=True)
    for key, value in payload.items():
        await db.platform_settings.update_one(
            {"key": key},
            {"$set": {"value": value, "updated_at": now_utc()},
             "$setOnInsert": {"_id": gen_id(), "key": key}},
            upsert=True,
        )
    await audit(None, user["_id"], "platform_settings.update", None, payload)
    return {"ok": True, **payload}

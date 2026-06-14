"""Super-admin routes: tenants (employers), audit, stats, platform settings."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db import db, employer_db
from ..deps import require_role
from ..schemas import CreateEmployerRequest, PlatformSettingsUpdate
from ..security import hash_password
from ..services.audit import audit
from ..services.seed import default_leave_types
from ..utils import gen_id, gen_signup_code, now_utc, public_user, today_iso

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/employers")
async def create_employer(
    req: CreateEmployerRequest, user: dict = Depends(require_role("super_admin"))
):
    admin_email = req.admin_email.lower().strip()
    if await db.users.find_one({"email": admin_email}):
        raise HTTPException(status_code=400, detail="Email already in use")

    # Generate an 8-char invite code that's globally unique. Collision space
    # is 31^8 ≈ 8.5e11; retry loop is theoretical defence in depth.
    signup_code = ""
    for _ in range(8):
        candidate = gen_signup_code()
        if not await db.employers.find_one({"signup_code": candidate}):
            signup_code = candidate
            break
    if not signup_code:
        raise HTTPException(status_code=500, detail="Could not allocate invite code, please retry")

    employer_id = gen_id()
    await db.employers.insert_one({
        "_id": employer_id,
        "name": req.name,
        "address": req.address,
        "phone": req.phone,
        "signup_code": signup_code,
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
        # New employers start with Payroll enabled by default. Super admin
        # can flip on additional modules (e.g. "students") via the features UI.
        "enabled_features": ["payroll"],
    })
    employer_user_id = gen_id()
    await db.users.insert_one({
        "_id": employer_user_id,
        "email": admin_email,
        "password_hash": hash_password(req.admin_password),
        "name": req.admin_name,
        "role": "employer",
        "employer_id": employer_id,
        "feature_permissions": ["payroll"],
        "created_at": now_utc(),
    })
    await audit(employer_id, user["_id"], "tenant.create", employer_id, {"name": req.name, "signup_code": signup_code})
    return {"id": employer_id, "admin_user_id": employer_user_id, "signup_code": signup_code}


@router.get("/employers")
async def list_employers(user: dict = Depends(require_role("super_admin"))):
    out = []
    async for t in db.employers.find({}, {}).sort("created_at", -1):
        admin = await db.users.find_one(
            {"employer_id": t["_id"], "role": "employer"}, {"password_hash": 0}
        )
        emp_count = await employer_db(t["_id"]).employees.count_documents({"employer_id": t["_id"]})
        t["id"] = t["_id"]
        t["admin"] = public_user(admin)
        t["employee_count"] = emp_count
        # Default to ["payroll"] for legacy tenants that haven't been backfilled yet.
        t["enabled_features"] = t.get("enabled_features") or ["payroll"]
        out.append({k: v for k, v in t.items() if k != "_id"})
    return out


@router.delete("/employers/{employer_id}")
async def delete_employer(employer_id: str, user: dict = Depends(require_role("super_admin"))):
    tdb = employer_db(employer_id)
    await db.employers.delete_one({"_id": employer_id})
    await db.users.delete_many({"employer_id": employer_id})
    await tdb.employees.delete_many({"employer_id": employer_id})
    await tdb.attendance.delete_many({"employer_id": employer_id})
    await tdb.leave_applications.delete_many({"employer_id": employer_id})
    await tdb.leave_balances.delete_many({"employer_id": employer_id})
    await tdb.payroll_runs.delete_many({"employer_id": employer_id})
    await tdb.payroll_items.delete_many({"employer_id": employer_id})
    await audit(None, user["_id"], "tenant.delete", employer_id)
    return {"ok": True}


@router.get("/audit")
async def list_audit(user: dict = Depends(require_role("super_admin")), limit: int = 100):
    items = []
    # Aggregate audits across every tenant DB.
    async for t in db.employers.find({}):
        tdb = employer_db(t["_id"])
        async for a in tdb.audit_logs.find().sort("created_at", -1).limit(limit):
            a["id"] = a["_id"]
            items.append({k: v for k, v in a.items() if k != "_id"})
    items.sort(key=lambda x: x.get("created_at"), reverse=True)
    return items[:limit]


@router.get("/stats")
async def admin_stats(user: dict = Depends(require_role("super_admin"))):
    employees = 0
    attendance_today = 0
    active_payrolls = 0
    today = today_iso()
    async for t in db.employers.find({}):
        tdb = employer_db(t["_id"])
        employees += await tdb.employees.count_documents({})
        attendance_today += await tdb.attendance.count_documents({"date": today})
        active_payrolls += await tdb.payroll_runs.count_documents(
            {"status": {"$in": ["draft", "pending_approval", "approved"]}}
        )
    employers_count = await db.employers.count_documents({})
    return {
        # Keep `tenants` as a back-compat alias for in-flight admin UIs;
        # new code should read `employers`.
        "tenants": employers_count,
        "employers": employers_count,
        "employees": employees,
        "attendance_today": attendance_today,
        "active_payrolls": active_payrolls,
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

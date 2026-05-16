"""Privacy / DPDP routes — consent, data export, erasure."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import db, tenant_db
from ..deps import get_current_user, require_role
from ..services.audit import audit
from ..utils import gen_id, now_utc

router = APIRouter(prefix="/me", tags=["privacy"])

# Keys we ask consent for. Add new keys here as the app evolves.
CONSENT_KEYS = [
    "data_processing",   # mandatory baseline — required to use the app
    "face_capture",      # facial liveness for attendance
    "geo_location",      # GPS share for attendance + geo-fence
    "whatsapp_email",    # transactional notifications
]
MANDATORY_KEYS = {"data_processing"}

ERASURE_NOTICE_DAYS = 30


class ConsentSet(BaseModel):
    consents: dict  # { key: bool }


@router.get("/privacy")
async def my_privacy(user: dict = Depends(get_current_user)):
    tdb = tenant_db(user["tenant_id"])
    """Return current consents + erasure request state."""
    consents_doc = await tdb.user_consents.find_one({"user_id": user["_id"]}) or {}
    consents = consents_doc.get("consents", {})
    erasure = await tdb.erasure_requests.find_one({"user_id": user["_id"], "status": "pending"})
    return {
        "consents": {k: bool(consents.get(k)) for k in CONSENT_KEYS},
        "consent_keys": CONSENT_KEYS,
        "mandatory_keys": list(MANDATORY_KEYS),
        "erasure_request": (
            {
                "id": erasure["_id"],
                "requested_at": erasure["requested_at"],
                "scheduled_for": erasure["scheduled_for"],
                "status": erasure["status"],
            }
            if erasure
            else None
        ),
        "needs_initial_consent": (
            consents_doc == {} or not all(k in consents for k in CONSENT_KEYS)
        ),
    }


@router.put("/privacy/consents")
async def set_consents(req: ConsentSet, user: dict = Depends(get_current_user)):
    tdb = tenant_db(user["tenant_id"])
    """Record / update user consents. Mandatory keys must be true."""
    payload = {k: bool(req.consents.get(k)) for k in CONSENT_KEYS}
    for k in MANDATORY_KEYS:
        if not payload.get(k):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot withdraw mandatory consent: {k}. Use the erasure flow to delete your account instead.",
            )
    await tdb.user_consents.update_one(
        {"user_id": user["_id"]},
        {
            "$set": {
                "consents": payload,
                "updated_at": now_utc(),
                "tenant_id": user.get("tenant_id"),
            },
            "$setOnInsert": {"_id": gen_id(), "user_id": user["_id"], "created_at": now_utc()},
        },
        upsert=True,
    )
    await audit(user.get("tenant_id"), user["_id"], "consent.update", user["_id"], payload)
    return {"ok": True, "consents": payload}


@router.get("/data-export")
async def export_my_data(user: dict = Depends(get_current_user)):
    tdb = tenant_db(user["tenant_id"])
    """DPDP §11 — Right to access. Returns every doc that contains this user's data."""
    user_id = user["_id"]
    employee_id = user.get("employee_id")

    bundle: dict = {
        "exported_at": now_utc().isoformat(),
        "user": {
            "id": user["_id"],
            "email": user["email"],
            "name": user.get("name"),
            "role": user["role"],
            "phone": user.get("phone"),
            "elevated_roles": user.get("elevated_roles", []),
            "created_at": user.get("created_at").isoformat() if user.get("created_at") else None,
        },
        "consents": (await tdb.user_consents.find_one({"user_id": user_id}) or {}).get("consents", {}),
    }
    if employee_id:
        emp = await tdb.employees.find_one({"_id": employee_id})
        if emp:
            emp.pop("_id", None)
            bundle["employee"] = emp
        bundle["attendance"] = []
        async for r in tdb.attendance.find({"employee_id": employee_id}).sort("date", -1):
            r.pop("_id", None)
            bundle["attendance"].append(r)
        bundle["leaves"] = []
        async for r in tdb.leave_applications.find({"employee_id": employee_id}).sort("applied_at", -1):
            r.pop("_id", None)
            bundle["leaves"].append(r)
        bundle["leave_balances"] = []
        async for r in tdb.leave_balances.find({"employee_id": employee_id}):
            r.pop("_id", None)
            bundle["leave_balances"].append(r)
        bundle["payroll_items"] = []
        async for r in tdb.payroll_items.find({"employee_id": employee_id}).sort("created_at", -1):
            r.pop("_id", None)
            bundle["payroll_items"].append(r)
    await audit(user.get("tenant_id"), user_id, "privacy.data_export", user_id)
    headers = {"Content-Disposition": f'attachment; filename="my-data-{user_id[:8]}.json"'}
    return JSONResponse(bundle, headers=headers)


@router.post("/erasure-request")
async def request_erasure(user: dict = Depends(get_current_user)):
    tdb = tenant_db(user["tenant_id"])
    """DPDP §12 — Right to correction & erasure. Schedules account deletion in 30 days."""
    if user["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Super Admin cannot erase via this flow")
    existing = await tdb.erasure_requests.find_one({"user_id": user["_id"], "status": "pending"})
    if existing:
        raise HTTPException(status_code=400, detail="Erasure already scheduled")
    rid = gen_id()
    scheduled = now_utc() + timedelta(days=ERASURE_NOTICE_DAYS)
    await tdb.erasure_requests.insert_one(
        {
            "_id": rid,
            "user_id": user["_id"],
            "tenant_id": user.get("tenant_id"),
            "employee_id": user.get("employee_id"),
            "requested_at": now_utc(),
            "scheduled_for": scheduled,
            "status": "pending",
        }
    )
    await audit(user.get("tenant_id"), user["_id"], "privacy.erasure_request", user["_id"], {"scheduled_for": scheduled.isoformat()})
    return {"id": rid, "scheduled_for": scheduled.isoformat()}


@router.delete("/erasure-request")
async def cancel_erasure(user: dict = Depends(get_current_user)):
    tdb = tenant_db(user["tenant_id"])
    res = await tdb.erasure_requests.update_one(
        {"user_id": user["_id"], "status": "pending"},
        {"$set": {"status": "cancelled", "cancelled_at": now_utc()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="No pending request")
    await audit(user.get("tenant_id"), user["_id"], "privacy.erasure_cancel", user["_id"])
    return {"ok": True}

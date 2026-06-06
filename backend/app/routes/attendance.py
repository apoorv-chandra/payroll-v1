"""Attendance routes — supports backdated marking when payroll not finalized."""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import db, tenant_db
from ..deps import get_current_user, require_role
from ..schemas import MarkAttendanceRequest, AttendanceDeleteRequest
from ..utils import app_tz, gen_id, haversine_m, now_utc, today_iso, strip_id

router = APIRouter(prefix="/attendance", tags=["attendance"])


async def _payroll_finalized(tenant_id: str, the_date: str) -> bool:
    """A month is locked once a payroll run is approved or disbursed."""
    tdb = tenant_db(tenant_id)
    d = date.fromisoformat(the_date)
    run = await tdb.payroll_runs.find_one({
        "tenant_id": tenant_id,
        "month": d.month,
        "year": d.year,
        "status": {"$in": ["approved", "disbursed"]},
    })
    return bool(run)


async def _max_backdate_days() -> int:
    s = await db.platform_settings.find_one({"key": "max_backdate_days"})
    return int((s or {}).get("value", 30))


@router.post("/mark")
async def mark_attendance(
    req: MarkAttendanceRequest, user: dict = Depends(require_role("employee"))
):
    tdb = tenant_db(user["tenant_id"])
    emp_id = user.get("employee_id")
    if not emp_id:
        raise HTTPException(status_code=400, detail="No employee profile linked")
    employee = await tdb.employees.find_one({"_id": emp_id})
    if not employee or not employee.get("active", True):
        raise HTTPException(status_code=403, detail="Employee inactive")

    target_date = req.date or today_iso()
    try:
        td = date.fromisoformat(target_date)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date")
    # Use the business timezone for the "what day is it" check so we don't
    # reject legitimate late-night IST marks while the UTC server is still on
    # the previous day.
    today_d = datetime.now(app_tz()).date()
    if td > today_d:
        raise HTTPException(status_code=400, detail="Cannot mark attendance for a future date")
    max_back = await _max_backdate_days()
    if (today_d - td).days > max_back:
        raise HTTPException(status_code=400, detail=f"Date is older than the {max_back}-day backdate limit")

    # ✅ DPDP: enforce consent for sensitive collection
    consents = (await tdb.user_consents.find_one({"user_id": user["_id"]}) or {}).get("consents", {})
    if req.method in ("facial", "facial_voice") and not consents.get("face_capture"):
        raise HTTPException(status_code=400, detail="Face capture consent not granted. Update your privacy preferences.")
    if (req.latitude is not None or req.longitude is not None) and not consents.get("geo_location"):
        raise HTTPException(status_code=400, detail="Location consent not granted. Update your privacy preferences.")

    if await _payroll_finalized(user["tenant_id"], target_date):
        raise HTTPException(
            status_code=400,
            detail="Payroll for this month has already been approved. Ask your employer to delete the payroll run first.",
        )

    tenant = await db.tenants.find_one({"_id": user["tenant_id"]})
    att_cfg = (tenant or {}).get("settings", {}).get("attendance", {})
    geo = att_cfg.get("geo_fence", {}) or {}

    within_fence = True
    if geo.get("enabled"):
        if req.latitude is None or req.longitude is None:
            raise HTTPException(status_code=400, detail="Location required")
        dist = haversine_m(req.latitude, req.longitude, geo["center_lat"], geo["center_lng"])
        within_fence = dist <= float(geo.get("radius_m", 100))
        if not within_fence:
            raise HTTPException(status_code=400, detail=f"Outside geo-fence ({int(dist)}m away)")

    now = now_utc()
    facial_hash = (
        hashlib.sha256(req.facial_image.encode("utf-8")).hexdigest()[:32]
        if req.facial_image
        else None
    )

    existing = await tdb.attendance.find_one({
        "tenant_id": user["tenant_id"],
        "employee_id": emp_id,
        "date": target_date,
    })

    if existing and req.overwrite:
        # Replace the entire record — only allowed because payroll is not finalized.
        await tdb.attendance.delete_one({"_id": existing["_id"]})
        existing = None

    if not existing:
        if req.type != "check_in":
            raise HTTPException(status_code=400, detail="Must check-in first")
        await tdb.attendance.insert_one({
            "_id": gen_id(),
            "tenant_id": user["tenant_id"],
            "employee_id": emp_id,
            "date": target_date,
            "check_in_at": now,
            "check_in_lat": req.latitude,
            "check_in_lng": req.longitude,
            "check_in_method": req.method,
            "check_in_facial_hash": facial_hash,
            "within_fence": within_fence,
            "status": "present",
            "is_backdated": target_date != today_iso(),
            "created_at": now,
        })
        return {"ok": True, "type": "check_in", "at": now.isoformat(), "date": target_date}

    if req.type != "check_out":
        raise HTTPException(status_code=400, detail="Already checked-in for this date")
    if existing.get("check_out_at"):
        raise HTTPException(status_code=400, detail="Already checked-out")
    await tdb.attendance.update_one(
        {"_id": existing["_id"]},
        {"$set": {
            "check_out_at": now,
            "check_out_lat": req.latitude,
            "check_out_lng": req.longitude,
            "check_out_method": req.method,
            "check_out_facial_hash": facial_hash,
        }},
    )
    return {"ok": True, "type": "check_out", "at": now.isoformat(), "date": target_date}


@router.post("/delete")
async def delete_attendance(
    req: AttendanceDeleteRequest, user: dict = Depends(require_role("employee"))
):
    tdb = tenant_db(user["tenant_id"])
    if await _payroll_finalized(user["tenant_id"], req.date):
        raise HTTPException(status_code=400, detail="Payroll already approved for this month")
    await tdb.attendance.delete_one({
        "tenant_id": user["tenant_id"],
        "employee_id": user["employee_id"],
        "date": req.date,
    })
    return {"ok": True}


@router.get("/today")
async def attendance_today(user: dict = Depends(require_role("employee"))):
    tdb = tenant_db(user["tenant_id"])
    emp_id = user["employee_id"]
    today = today_iso()
    rec = await tdb.attendance.find_one(
        {"tenant_id": user["tenant_id"], "employee_id": emp_id, "date": today}
    )
    if not rec:
        return {"date": today, "marked": False}
    return {"date": today, "marked": True, "record": strip_id(rec)}


@router.get("/history")
async def attendance_history(
    month: Optional[int] = None,
    year: Optional[int] = None,
    employee_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    tdb = tenant_db(user["tenant_id"])
    today = datetime.now(app_tz()).date()
    m = month or today.month
    y = year or today.year
    start = date(y, m, 1).isoformat()
    end = (date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)).isoformat()

    if user["role"] == "employee":
        query = {
            "tenant_id": user["tenant_id"],
            "employee_id": user["employee_id"],
            "date": {"$gte": start, "$lt": end},
        }
    elif user["role"] == "employer":
        query = {"tenant_id": user["tenant_id"], "date": {"$gte": start, "$lt": end}}
        if employee_id:
            query["employee_id"] = employee_id
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    out = []
    async for r in tdb.attendance.find(query).sort("date", -1):
        out.append(strip_id(r))
    return out


@router.get("/locked-months")
async def locked_months(user: dict = Depends(require_role("employee"))):
    tdb = tenant_db(user["tenant_id"])
    """Months for which payroll is approved/disbursed — UI hides edit affordances."""
    out = []
    async for r in tdb.payroll_runs.find({
        "tenant_id": user["tenant_id"],
        "status": {"$in": ["approved", "disbursed"]},
    }):
        out.append({"month": r["month"], "year": r["year"]})
    return out


@router.get("/config")
async def attendance_config(user: dict = Depends(require_role("employee"))):
    tdb = tenant_db(user["tenant_id"])
    """Returns effective attendance requirements for THIS employee.

    Config IDs (legacy enumeration):
      1 = Tap only
      2 = Tap + Geo location (capture)
      3 = Tap + Geo fence (enforced)
      4 = Tap + Both
      5 = Facial
      6 = Facial + Geo location
      7 = Facial + Geo fence
      8 = Facial + Both
    """
    tenant = await db.tenants.find_one({"_id": user["tenant_id"]}) or {}
    att = (tenant.get("settings") or {}).get("attendance") or {}
    geo_cfg = att.get("geo_fence") or {}

    # Per-employee override falls back to tenant default.
    emp = await tdb.employees.find_one({"user_id": user["_id"]}) or {}
    config_id = int(emp.get("attendance_config_id") or att.get("default_config_id") or 1)

    requires_facial = config_id in (5, 6, 7, 8)
    requires_geo = config_id in (2, 3, 4, 6, 7, 8)
    geo_fence_enforced = config_id in (3, 4, 7, 8) and bool(geo_cfg.get("enabled"))

    return {
        "max_backdate_days": await _max_backdate_days(),
        "config_id": config_id,
        "requires_facial": requires_facial,
        "requires_geo": requires_geo,
        "geo_fence_enforced": geo_fence_enforced,
    }


# ---------------- Location history ----------------

@router.get("/locations/me")
async def my_locations(user: dict = Depends(require_role("employee")), limit: int = 60):
    """Date-wise list of stored check-in/out coordinates for the logged-in
    employee. Only records where the employee had `geo_location` consent at
    mark time appear here (the mark route enforces that)."""
    tdb = tenant_db(user["tenant_id"])
    emp = await tdb.employees.find_one({"user_id": user["_id"]}) or {}
    if not emp:
        return []
    return await _location_history(tdb, emp["_id"], limit)


@router.get("/locations/{employee_id}")
async def employee_locations(
    employee_id: str,
    user: dict = Depends(get_current_user),
    limit: int = 60,
):
    """Employer / accountant view of one employee's date-wise locations."""
    if user["role"] != "employer" and "accountant" not in (user.get("elevated_roles") or []):
        raise HTTPException(status_code=403, detail="Forbidden")
    tdb = tenant_db(user["tenant_id"])
    emp = await tdb.employees.find_one({"_id": employee_id})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await _location_history(tdb, employee_id, limit)


async def _location_history(tdb, employee_id: str, limit: int) -> list[dict]:
    out: list[dict] = []
    cursor = (
        tdb.attendance.find(
            {
                "employee_id": employee_id,
                "$or": [
                    {"check_in_lat": {"$ne": None}},
                    {"check_out_lat": {"$ne": None}},
                ],
            }
        )
        .sort("date", -1)
        .limit(limit)
    )
    async for a in cursor:
        out.append(
            {
                "id": a["_id"],
                "date": a["date"],
                "check_in_at": a.get("check_in_at"),
                "check_in_lat": a.get("check_in_lat"),
                "check_in_lng": a.get("check_in_lng"),
                "check_out_at": a.get("check_out_at"),
                "check_out_lat": a.get("check_out_lat"),
                "check_out_lng": a.get("check_out_lng"),
                "accuracy": a.get("accuracy"),
            }
        )
    return out


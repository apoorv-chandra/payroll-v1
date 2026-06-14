"""Leave routes."""
from __future__ import annotations

import asyncio
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from ..db import db, employer_db
from ..deps import get_current_user, require_role
from ..schemas import ApplyLeaveRequest, LeaveDecision
from ..services.audit import audit
from ..services.whatsapp import send_whatsapp, msg_leave_decision
from ..utils import gen_id, now_utc

router = APIRouter(prefix="/leave", tags=["leave"])


@router.get("/balances")
async def my_leave_balances(user: dict = Depends(require_role("employee"))):
    tdb = employer_db(user["employer_id"])
    out = []
    async for b in tdb.leave_balances.find({
        "employer_id": user["employer_id"],
        "employee_id": user["employee_id"],
    }):
        b["id"] = b["_id"]
        out.append({k: v for k, v in b.items() if k != "_id"})
    return out


@router.post("/apply")
async def apply_leave(req: ApplyLeaveRequest, user: dict = Depends(require_role("employee"))):
    tdb = employer_db(user["employer_id"])
    try:
        d_from = date.fromisoformat(req.from_date)
        d_to = date.fromisoformat(req.to_date)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid dates")
    if d_to < d_from:
        raise HTTPException(status_code=400, detail="to_date < from_date")
    days = 0.5 if req.half_day else (d_to - d_from).days + 1
    bal = await tdb.leave_balances.find_one({
        "employer_id": user["employer_id"],
        "employee_id": user["employee_id"],
        "leave_type": req.leave_type,
    })
    if not bal:
        raise HTTPException(status_code=400, detail="Unknown leave type")
    available = bal["quota"] - bal.get("used", 0) - bal.get("pending", 0)
    if days > available and bal["quota"] > 0:
        raise HTTPException(status_code=400, detail=f"Insufficient balance ({available} days left)")
    app_id = gen_id()
    await tdb.leave_applications.insert_one({
        "_id": app_id,
        "employer_id": user["employer_id"],
        "employee_id": user["employee_id"],
        "leave_type": req.leave_type,
        "from_date": req.from_date,
        "to_date": req.to_date,
        "days": days,
        "half_day": req.half_day,
        "reason": req.reason,
        "status": "pending",
        "applied_at": now_utc(),
    })
    await tdb.leave_balances.update_one({"_id": bal["_id"]}, {"$inc": {"pending": days}})
    return {"id": app_id}


@router.get("/applications")
async def list_leave_apps(status_f: str | None = None, user: dict = Depends(get_current_user)):
    tdb = employer_db(user["employer_id"])
    if user["role"] == "employee":
        q = {"employer_id": user["employer_id"], "employee_id": user["employee_id"]}
    elif user["role"] == "employer":
        q = {"employer_id": user["employer_id"]}
    else:
        raise HTTPException(status_code=403, detail="Forbidden")
    if status_f:
        q["status"] = status_f
    out = []
    async for a in tdb.leave_applications.find(q).sort("applied_at", -1):
        a["id"] = a["_id"]
        emp = await tdb.employees.find_one(
            {"_id": a["employee_id"]}, {"name": 1, "emp_code": 1, "phone": 1}
        )
        a["employee_name"] = emp["name"] if emp else None
        a["employee_code"] = emp["emp_code"] if emp else None
        out.append({k: v for k, v in a.items() if k != "_id"})
    return out


@router.post("/applications/{app_id}/decision")
async def decide_leave(
    app_id: str, req: LeaveDecision, user: dict = Depends(get_current_user)
):
    tdb = employer_db(user["employer_id"])
    if user["role"] != "employer" and "principal" not in user.get("elevated_roles", []):
        raise HTTPException(status_code=403, detail="Forbidden")
    app = await tdb.leave_applications.find_one(
        {"_id": app_id, "employer_id": user["employer_id"]}
    )
    if not app:
        raise HTTPException(status_code=404, detail="Not found")
    if app["status"] != "pending":
        raise HTTPException(status_code=400, detail="Already decided")
    bal = await tdb.leave_balances.find_one({
        "employer_id": user["employer_id"],
        "employee_id": app["employee_id"],
        "leave_type": app["leave_type"],
    })
    if not bal:
        raise HTTPException(status_code=400, detail="Balance missing")
    if req.decision == "approved":
        await tdb.leave_balances.update_one(
            {"_id": bal["_id"]},
            {"$inc": {"used": app["days"], "pending": -app["days"]}},
        )
    else:
        await tdb.leave_balances.update_one(
            {"_id": bal["_id"]}, {"$inc": {"pending": -app["days"]}}
        )
    decided_at = now_utc()
    await tdb.leave_applications.update_one(
        {"_id": app_id},
        {"$set": {
            "status": req.decision,
            "decided_by": user["_id"],
            "decided_at": decided_at,
            "decided_at_local": req.decided_at_local,
            "decision_note": req.note,
        }},
    )
    await audit(user["employer_id"], user["_id"], f"leave.{req.decision}", app_id)

    # WhatsApp notification (super-admin global flag controlled).
    emp = await tdb.employees.find_one({"_id": app["employee_id"]})
    if emp and emp.get("phone"):
        body = msg_leave_decision(
            name=emp["name"],
            leave_type=app["leave_type"],
            frm=app["from_date"],
            to=app["to_date"],
            decision=req.decision,
            decided_at_local=req.decided_at_local or decided_at.isoformat(),
            note=req.note,
        )
        asyncio.create_task(send_whatsapp(emp["phone"], body))
    return {"ok": True}

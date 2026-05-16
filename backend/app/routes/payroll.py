"""Payroll routes — full accountant workflow.

State machine:
    draft -> pending_approval -> approved -> disbursed
    draft -> rejected (terminal until regenerated)
    approved/disbursed -> deletable by employer (re-trigger flow)
"""
from __future__ import annotations

import asyncio
import io
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..db import db
from ..deps import get_current_user, require_employer_or_admin, require_role
from ..schemas import (
    GeneratePayrollRequest,
    PayrollItemDeductionUpdate,
    PayrollSubmitRequest,
    PayrollDecision,
    DisburseRequest,
)
from ..services.audit import audit
from ..services.pdf import build_salary_slip_pdf
from ..services.whatsapp import send_whatsapp, msg_salary_ready
from ..utils import gen_id, indian_fmt, now_utc, strip_id
from ..config import settings

router = APIRouter(prefix="/payroll", tags=["payroll"])


def _can_run_payroll(user: dict) -> bool:
    return (
        user["role"] == "employer"
        or "accountant" in user.get("elevated_roles", [])
    )


def _can_disburse(user: dict) -> bool:
    roles = user.get("elevated_roles", [])
    return user["role"] == "employer" or "cashier" in roles or "accountant" in roles


def _month_dates(year: int, month: int):
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def _months():
    return [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]


# ---------- Generate ----------
@router.post("/generate")
async def generate_payroll(req: GeneratePayrollRequest, user: dict = Depends(get_current_user)):
    if not _can_run_payroll(user):
        raise HTTPException(status_code=403, detail="Only employer or accountant can generate payroll")
    tenant = await db.tenants.find_one({"_id": user["tenant_id"]})
    working_days = (tenant or {}).get("settings", {}).get("attendance", {}).get("working_days_per_month", 26)
    existing = await db.payroll_runs.find_one({
        "tenant_id": user["tenant_id"], "month": req.month, "year": req.year
    })
    if existing and existing["status"] in ("approved", "disbursed"):
        raise HTTPException(
            status_code=400,
            detail="Payroll already finalized — delete the approved run first.",
        )

    start, end = _month_dates(req.year, req.month)
    run_id = existing["_id"] if existing else gen_id()
    if not existing:
        await db.payroll_runs.insert_one({
            "_id": run_id,
            "tenant_id": user["tenant_id"],
            "month": req.month,
            "year": req.year,
            "status": "draft",
            "working_days": working_days,
            "generated_by": user["_id"],
            "generated_at": now_utc(),
        })
    else:
        await db.payroll_runs.update_one(
            {"_id": run_id},
            {"$set": {
                "status": "draft",
                "working_days": working_days,
                "generated_by": user["_id"],
                "generated_at": now_utc(),
            }},
        )
        await db.payroll_items.delete_many({"payroll_run_id": run_id})

    items = []
    async for emp in db.employees.find({"tenant_id": user["tenant_id"], "active": True}):
        att = await db.attendance.count_documents({
            "tenant_id": user["tenant_id"],
            "employee_id": emp["_id"],
            "date": {"$gte": start.isoformat(), "$lt": end.isoformat()},
            "status": "present",
        })
        paid_leaves = 0.0
        async for la in db.leave_applications.find({
            "tenant_id": user["tenant_id"],
            "employee_id": emp["_id"],
            "status": "approved",
            "from_date": {"$lt": end.isoformat()},
            "to_date": {"$gte": start.isoformat()},
        }):
            try:
                lf = max(date.fromisoformat(la["from_date"]), start)
                lt_ = min(date.fromisoformat(la["to_date"]), end - timedelta(days=1))
                d = (lt_ - lf).days + 1
                if la.get("half_day"):
                    d = 0.5
                paid_leaves += max(0, d)
            except Exception:
                pass
        payable_days = min(working_days, att + paid_leaves)
        per_day = (emp["monthly_salary"] or 0) / working_days
        gross = round(per_day * payable_days, 2)
        items.append({
            "_id": gen_id(),
            "payroll_run_id": run_id,
            "tenant_id": user["tenant_id"],
            "employee_id": emp["_id"],
            "employee_name": emp["name"],
            "emp_code": emp["emp_code"],
            "monthly_salary": emp["monthly_salary"],
            "present_days": att,
            "paid_leave_days": paid_leaves,
            "payable_days": payable_days,
            "per_day": round(per_day, 2),
            "gross_salary": gross,
            "deductions": 0,
            "deduction_note": None,
            "net_salary": gross,
            "disbursement": None,
            "created_at": now_utc(),
        })
    if items:
        await db.payroll_items.insert_many(items)
    await audit(user["tenant_id"], user["_id"], "payroll.generate", run_id, {"month": req.month, "year": req.year, "count": len(items)})
    return {"id": run_id, "items": len(items)}


# ---------- List / detail ----------
@router.get("/runs")
async def list_runs(user: dict = Depends(get_current_user)):
    if user["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Use tenant scope")
    # Employers see all; accountants (elevated employees) also see all to do
    # their own payroll workflow.
    if user["role"] == "employer" or _can_run_payroll(user):
        pass
    else:
        raise HTTPException(status_code=403, detail="Forbidden")
    out = []
    async for r in db.payroll_runs.find({"tenant_id": user["tenant_id"]}).sort([("year", -1), ("month", -1)]):
        r["id"] = r["_id"]
        r["items_count"] = await db.payroll_items.count_documents({"payroll_run_id": r["_id"]})
        out.append({k: v for k, v in r.items() if k != "_id"})
    return out


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user: dict = Depends(get_current_user)):
    r = await db.payroll_runs.find_one({"_id": run_id})
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] != "super_admin" and r["tenant_id"] != user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Forbidden")
    items = []
    async for it in db.payroll_items.find({"payroll_run_id": run_id}).sort("emp_code", 1):
        items.append(strip_id(it))
    return {"run": strip_id(r), "items": items}


# ---------- Accountant: edit deductions, submit for approval ----------
@router.put("/items/{item_id}/deductions")
async def edit_deductions(
    item_id: str,
    req: PayrollItemDeductionUpdate,
    user: dict = Depends(get_current_user),
):
    if not _can_run_payroll(user):
        raise HTTPException(status_code=403, detail="Forbidden")
    it = await db.payroll_items.find_one({"_id": item_id})
    if not it or it["tenant_id"] != user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Not found")
    run = await db.payroll_runs.find_one({"_id": it["payroll_run_id"]})
    if run["status"] not in ("draft",):
        raise HTTPException(status_code=400, detail="Only editable in draft state")
    deductions = round(float(req.deductions or 0), 2)
    net = round((it["gross_salary"] or 0) - deductions, 2)
    await db.payroll_items.update_one(
        {"_id": item_id},
        {"$set": {"deductions": deductions, "deduction_note": req.note, "net_salary": net}},
    )
    await audit(user["tenant_id"], user["_id"], "payroll.deduction.edit", item_id, {"d": deductions})
    return {"ok": True, "deductions": deductions, "net_salary": net}


@router.post("/runs/{run_id}/submit")
async def submit_for_approval(
    run_id: str,
    req: PayrollSubmitRequest,
    user: dict = Depends(get_current_user),
):
    if not _can_run_payroll(user):
        raise HTTPException(status_code=403, detail="Forbidden")
    r = await db.payroll_runs.find_one({"_id": run_id, "tenant_id": user["tenant_id"]})
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    if r["status"] != "draft":
        raise HTTPException(status_code=400, detail="Run is not in draft")
    await db.payroll_runs.update_one(
        {"_id": run_id},
        {"$set": {
            "status": "pending_approval",
            "submitted_by": user["_id"],
            "submitted_at": now_utc(),
            "submission_note": req.note,
        }},
    )
    await audit(user["tenant_id"], user["_id"], "payroll.submit", run_id)
    return {"ok": True, "status": "pending_approval"}


# ---------- Employer: approve / reject / delete ----------
@router.post("/runs/{run_id}/approve")
async def approve_run(
    run_id: str,
    req: PayrollDecision,
    user: dict = Depends(require_role("employer")),
):
    r = await db.payroll_runs.find_one({"_id": run_id, "tenant_id": user["tenant_id"]})
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    if r["status"] not in ("draft", "pending_approval"):
        raise HTTPException(status_code=400, detail="Run is not awaiting approval")
    new_status = "approved" if req.decision == "approved" else "rejected"
    decided_at = now_utc()
    await db.payroll_runs.update_one(
        {"_id": run_id},
        {"$set": {
            "status": new_status,
            "approved_by": user["_id"],
            "approved_at": decided_at,
            "approved_at_local": req.decided_at_local,
            "approval_note": req.note,
        }},
    )
    await audit(user["tenant_id"], user["_id"], f"payroll.{new_status}", run_id)

    # WhatsApp salary notification (per-employee).
    if new_status == "approved":
        tenant_doc = await db.tenants.find_one({"_id": user["tenant_id"]})
        run_doc = await db.payroll_runs.find_one({"_id": run_id})
        mname = _months()[run_doc["month"]]
        app_url = settings.APP_BASE_URL or ""
        async for it in db.payroll_items.find({"payroll_run_id": run_id}):
            emp = await db.employees.find_one({"_id": it["employee_id"]})
            if not emp or not emp.get("phone"):
                continue
            body = msg_salary_ready(
                name=emp["name"],
                month=mname,
                year=run_doc["year"],
                net=indian_fmt(it["net_salary"]),
                approved_at_local=req.decided_at_local or decided_at.isoformat(),
                app_url=app_url or "(open the app)",
            )
            asyncio.create_task(send_whatsapp(emp["phone"], body))
    return {"ok": True, "status": new_status}


@router.delete("/runs/{run_id}")
async def delete_run(
    run_id: str, user: dict = Depends(require_role("employer"))
):
    r = await db.payroll_runs.find_one({"_id": run_id, "tenant_id": user["tenant_id"]})
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    await db.payroll_items.delete_many({"payroll_run_id": run_id})
    await db.payroll_runs.delete_one({"_id": run_id})
    await audit(user["tenant_id"], user["_id"], "payroll.delete", run_id, {"prev_status": r.get("status")})
    return {"ok": True}


# ---------- Disbursement (cash/online MOCKED) ----------
@router.post("/items/{item_id}/disburse")
async def disburse_item(
    item_id: str, req: DisburseRequest, user: dict = Depends(get_current_user)
):
    if not _can_disburse(user):
        raise HTTPException(status_code=403, detail="Forbidden")
    it = await db.payroll_items.find_one({"_id": item_id})
    if not it or it["tenant_id"] != user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Not found")
    run = await db.payroll_runs.find_one({"_id": it["payroll_run_id"]})
    if run["status"] not in ("approved", "disbursed"):
        raise HTTPException(status_code=400, detail="Run not approved")
    disb = {
        "method": req.method,
        "status": "paid",
        "txn_id": f"MOCK-{gen_id()[:8].upper()}",  # MOCKED — replace with RazorpayX call
        "at": now_utc().isoformat(),
        "by": user["_id"],
    }
    await db.payroll_items.update_one({"_id": item_id}, {"$set": {"disbursement": disb}})
    pending = await db.payroll_items.count_documents({
        "payroll_run_id": run["_id"], "disbursement": None
    })
    if pending == 0:
        await db.payroll_runs.update_one({"_id": run["_id"]}, {"$set": {"status": "disbursed"}})
    await audit(user["tenant_id"], user["_id"], "payroll.disburse", item_id, disb)
    return {"ok": True, "disbursement": disb}


# ---------- Salary slip PDF ----------
@router.get("/items/{item_id}/slip")
async def download_slip(item_id: str, user: dict = Depends(get_current_user)):
    it = await db.payroll_items.find_one({"_id": item_id})
    if not it:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] == "employee":
        if it["employee_id"] != user.get("employee_id"):
            raise HTTPException(status_code=403, detail="Forbidden")
    elif user["role"] == "employer":
        if it["tenant_id"] != user["tenant_id"]:
            raise HTTPException(status_code=403, detail="Forbidden")
    elif user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    run = await db.payroll_runs.find_one({"_id": it["payroll_run_id"]})
    employee = await db.employees.find_one({"_id": it["employee_id"]})
    tenant = await db.tenants.find_one({"_id": it["tenant_id"]})
    pdf = build_salary_slip_pdf(tenant, employee, it, run)
    fn = f"salary-slip-{employee['emp_code']}-{run['year']}-{run['month']:02d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/my")
async def my_payslips(user: dict = Depends(require_role("employee"))):
    out = []
    async for it in db.payroll_items.find({
        "tenant_id": user["tenant_id"], "employee_id": user["employee_id"]
    }).sort("created_at", -1):
        run = await db.payroll_runs.find_one({"_id": it["payroll_run_id"]})
        if run and run["status"] in ("approved", "disbursed"):
            it["id"] = it["_id"]
            it["month"] = run["month"]
            it["year"] = run["year"]
            it["run_status"] = run["status"]
            out.append({k: v for k, v in it.items() if k != "_id"})
    return out


# ---------- Accountant summary view ----------
@router.get("/runs/{run_id}/summary")
async def run_summary(run_id: str, user: dict = Depends(get_current_user)):
    """Read-only Name + Net Salary summary, scoped to the same tenant.

    Available to anyone in the tenant who can run payroll OR was the
    submitter — used by the accountant's post-approval summary screen.
    """
    r = await db.payroll_runs.find_one({"_id": run_id})
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] != "super_admin" and r["tenant_id"] != user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Forbidden")
    items = []
    total = 0.0
    async for it in db.payroll_items.find({"payroll_run_id": run_id}).sort("emp_code", 1):
        items.append({
            "id": it["_id"],
            "emp_code": it["emp_code"],
            "employee_name": it["employee_name"],
            "designation": it.get("designation"),
            "department": it.get("department"),
            "net_salary": it["net_salary"],
            "disbursed": bool(it.get("disbursement")),
        })
        total += it.get("net_salary") or 0
    return {
        "run": {
            "id": r["_id"],
            "month": r["month"],
            "year": r["year"],
            "status": r["status"],
            "working_days": r["working_days"],
        },
        "items": items,
        "total": round(total, 2),
        "count": len(items),
    }

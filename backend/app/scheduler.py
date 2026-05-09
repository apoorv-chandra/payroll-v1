"""Background scheduled jobs.

Two cron-style jobs run inside the FastAPI process via APScheduler:

1. **monthly_payroll_auto_draft** — on the 1st of every month at 02:00 server
   time, generate a *draft* payroll run for the previous month for every
   tenant + employee (only if no run exists for that month). The
   accountant / employer must still review and approve.

2. **process_erasure_requests** — daily at 03:00. Hard-deletes any user
   that filed an erasure request more than 30 days ago.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .db import db
from .utils import gen_id, now_utc

logger = logging.getLogger(__name__)

scheduler: AsyncIOScheduler | None = None


async def monthly_payroll_auto_draft() -> None:
    today = date.today()
    last_day_prev = today.replace(day=1) - timedelta(days=1)
    target_month, target_year = last_day_prev.month, last_day_prev.year
    logger.info("[cron] payroll auto-draft for %s/%s", target_month, target_year)

    async for tenant in db.tenants.find({"active": True}):
        existing = await db.payroll_runs.find_one(
            {"tenant_id": tenant["_id"], "month": target_month, "year": target_year}
        )
        if existing:
            continue
        # Generate draft (logic mirrors /api/payroll/generate but synchronous and
        # owned by a synthetic 'system' actor to keep state machines clean).
        from .routes.payroll import _month_dates
        from datetime import timedelta as _td

        working_days = (
            tenant.get("settings", {})
            .get("attendance", {})
            .get("working_days_per_month", 26)
        )
        run_id = gen_id()
        await db.payroll_runs.insert_one(
            {
                "_id": run_id,
                "tenant_id": tenant["_id"],
                "month": target_month,
                "year": target_year,
                "status": "draft",
                "working_days": working_days,
                "generated_by": "system",
                "generated_at": now_utc(),
                "auto_drafted": True,
            }
        )
        start, end = _month_dates(target_year, target_month)
        items = []
        async for emp in db.employees.find({"tenant_id": tenant["_id"], "active": True}):
            att = await db.attendance.count_documents(
                {
                    "tenant_id": tenant["_id"],
                    "employee_id": emp["_id"],
                    "date": {"$gte": start.isoformat(), "$lt": end.isoformat()},
                    "status": "present",
                }
            )
            paid_leaves = 0.0
            async for la in db.leave_applications.find(
                {
                    "tenant_id": tenant["_id"],
                    "employee_id": emp["_id"],
                    "status": "approved",
                    "from_date": {"$lt": end.isoformat()},
                    "to_date": {"$gte": start.isoformat()},
                }
            ):
                try:
                    from datetime import date as _d
                    lf = max(_d.fromisoformat(la["from_date"]), start)
                    lt_ = min(_d.fromisoformat(la["to_date"]), end - _td(days=1))
                    d = (lt_ - lf).days + 1
                    if la.get("half_day"):
                        d = 0.5
                    paid_leaves += max(0, d)
                except Exception:
                    pass
            payable_days = min(working_days, att + paid_leaves)
            per_day = (emp.get("monthly_salary") or 0) / working_days
            gross = round(per_day * payable_days, 2)
            items.append(
                {
                    "_id": gen_id(),
                    "payroll_run_id": run_id,
                    "tenant_id": tenant["_id"],
                    "employee_id": emp["_id"],
                    "employee_name": emp["name"],
                    "emp_code": emp["emp_code"],
                    "monthly_salary": emp.get("monthly_salary", 0),
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
                }
            )
        if items:
            await db.payroll_items.insert_many(items)
        await db.audit_logs.insert_one(
            {
                "_id": gen_id(),
                "tenant_id": tenant["_id"],
                "actor_id": "system",
                "action": "payroll.auto_draft",
                "target": run_id,
                "meta": {"month": target_month, "year": target_year, "items": len(items)},
                "created_at": now_utc(),
            }
        )
        logger.info(
            "[cron] auto-drafted run %s for tenant %s (%d items)",
            run_id,
            tenant["_id"],
            len(items),
        )


async def process_erasure_requests() -> None:
    """Hard-delete users whose erasure request has aged past the notice period."""
    now = now_utc()
    async for req in db.erasure_requests.find({"status": "pending"}):
        if req["scheduled_for"].replace(tzinfo=None) > now.replace(tzinfo=None):
            continue
        user_id = req["user_id"]
        employee_id = req.get("employee_id")
        # Hard delete user + linked records. Audit kept (anonymised actor).
        await db.users.delete_one({"_id": user_id})
        await db.user_consents.delete_many({"user_id": user_id})
        if employee_id:
            await db.employees.delete_one({"_id": employee_id})
            await db.attendance.delete_many({"employee_id": employee_id})
            await db.leave_applications.delete_many({"employee_id": employee_id})
            await db.leave_balances.delete_many({"employee_id": employee_id})
            await db.payroll_items.delete_many({"employee_id": employee_id})
        await db.erasure_requests.update_one(
            {"_id": req["_id"]},
            {"$set": {"status": "completed", "completed_at": now}},
        )
        await db.audit_logs.insert_one(
            {
                "_id": gen_id(),
                "tenant_id": req.get("tenant_id"),
                "actor_id": "system",
                "action": "privacy.erasure_complete",
                "target": user_id,
                "meta": {"request_id": req["_id"]},
                "created_at": now,
            }
        )
        logger.info("[cron] erased user=%s employee=%s", user_id, employee_id)


def start_scheduler() -> None:
    global scheduler
    if scheduler is not None:
        return
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    # 02:00 IST on the 1st of every month
    scheduler.add_job(
        monthly_payroll_auto_draft,
        CronTrigger(day=1, hour=2, minute=0),
        id="monthly_payroll_auto_draft",
        replace_existing=True,
    )
    # 03:00 IST every day
    scheduler.add_job(
        process_erasure_requests,
        CronTrigger(hour=3, minute=0),
        id="process_erasure_requests",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started (timezone=Asia/Kolkata)")


def stop_scheduler() -> None:
    global scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None

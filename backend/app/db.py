"""MongoDB client + database accessor."""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from .config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URL)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.DB_NAME]


db = get_db()


async def ensure_indexes() -> None:
    await db.users.create_index("email", unique=True)
    await db.tenants.create_index("name")
    await db.employees.create_index([("tenant_id", 1), ("emp_code", 1)], unique=True)
    await db.employees.create_index([("tenant_id", 1), ("user_id", 1)])
    await db.attendance.create_index(
        [("tenant_id", 1), ("employee_id", 1), ("date", 1)], unique=True
    )
    await db.leave_applications.create_index([("tenant_id", 1), ("employee_id", 1)])
    await db.leave_balances.create_index(
        [("tenant_id", 1), ("employee_id", 1), ("leave_type", 1)], unique=True
    )
    await db.payroll_runs.create_index([("tenant_id", 1), ("month", 1), ("year", 1)])
    await db.payroll_items.create_index(
        [("payroll_run_id", 1), ("employee_id", 1)], unique=True
    )
    await db.audit_logs.create_index([("tenant_id", 1), ("created_at", -1)])
    await db.captchas.create_index("expires_at", expireAfterSeconds=0)
    await db.platform_settings.create_index("key", unique=True)

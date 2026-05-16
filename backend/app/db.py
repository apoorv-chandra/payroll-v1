"""MongoDB client + per-tenant database accessor.

Architecture: hybrid.
  • Global database (`settings.DB_NAME`) holds cross-tenant primitives:
      tenants, users, captchas, platform_settings.
    Auth must look up users by email regardless of tenant, so users live here.
  • Per-tenant database (`{settings.DB_NAME}_t_<safe_tenant_id>`) holds the
    rest: employees, attendance, leaves, leave_balances, payroll_runs,
    payroll_items, audit_logs, user_consents, erasure_requests.
    Strong physical isolation; one client cannot see another's data even
    in the case of a code-level bug omitting `tenant_id` filters.
"""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from .config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URL)
    return _client


def global_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.DB_NAME]


# Backward-compat alias — `db` always refers to the GLOBAL database.
# Routes that operate on tenant-scoped data MUST switch to `tenant_db(tid)`.
db = global_db()


def _safe_tenant_suffix(tenant_id: str) -> str:
    """Mongo db names disallow .$/\\ space NUL — UUIDs only have hex+dashes,
    we strip dashes for cleaner names."""
    return (tenant_id or "").replace("-", "").replace(".", "")


def tenant_db(tenant_id: str) -> AsyncIOMotorDatabase:
    """Return the database handle for `tenant_id`. Caller is responsible for
    ensuring `tenant_id` belongs to the authenticated user."""
    if not tenant_id:
        raise ValueError("tenant_db() requires a tenant_id")
    return get_client()[f"{settings.DB_NAME}_t_{_safe_tenant_suffix(tenant_id)}"]


# Per-tenant collections that we migrate from the legacy shared DB.
PER_TENANT_COLLECTIONS = (
    "employees",
    "attendance",
    "leave_applications",
    "leave_balances",
    "payroll_runs",
    "payroll_items",
    "audit_logs",
    "user_consents",
    "erasure_requests",
)


async def ensure_indexes() -> None:
    # Global indexes — cross-tenant primitives.
    await db.users.create_index("email", unique=True)
    await db.tenants.create_index("name")
    await db.tenants.create_index("signup_code", unique=True, sparse=True)
    await db.captchas.create_index("expires_at", expireAfterSeconds=0)
    await db.platform_settings.create_index("key", unique=True)


async def ensure_tenant_indexes(tenant_id: str) -> None:
    """Create per-tenant indexes lazily — first time we touch a tenant DB."""
    tdb = tenant_db(tenant_id)
    await tdb.employees.create_index("emp_code", unique=True)
    await tdb.employees.create_index("user_id")
    await tdb.attendance.create_index([("employee_id", 1), ("date", 1)], unique=True)
    await tdb.leave_applications.create_index([("employee_id", 1)])
    await tdb.leave_balances.create_index(
        [("employee_id", 1), ("leave_type", 1)], unique=True
    )
    await tdb.payroll_runs.create_index([("month", 1), ("year", 1)])
    await tdb.payroll_items.create_index(
        [("payroll_run_id", 1), ("employee_id", 1)], unique=True
    )
    await tdb.audit_logs.create_index([("created_at", -1)])
    await tdb.user_consents.create_index("user_id", unique=True)
    await tdb.erasure_requests.create_index([("user_id", 1), ("status", 1)])

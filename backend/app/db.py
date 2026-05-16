"""MongoDB client + per-tenant database accessor.

Architecture: hybrid.
  • Global database (`settings.DB_NAME`) holds cross-tenant primitives:
      tenants, users, captchas, platform_settings.
    Auth must look up users by email regardless of tenant, so users live here.
  • Per-tenant database (`{settings.DB_NAME}_t_<short_hash>`) holds the
    rest: employees, attendance, leaves, leave_balances, payroll_runs,
    payroll_items, audit_logs, user_consents, erasure_requests.
    Strong physical isolation; one client cannot see another's data even
    in the case of a code-level bug omitting `tenant_id` filters.

Naming note: MongoDB Atlas caps DB names at 38 bytes, so we deterministically
hash the tenant_id with blake2s into 24 hex chars. Total length:
  len(DB_NAME) + 3 ("_t_") + 24  ≤ 38  → DB_NAME must stay ≤ 11 chars.
80-bit hash space (~10^24) is collision-free for the lifetime of the platform.
"""
from __future__ import annotations

import hashlib

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
    """24-hex-char blake2s digest of the tenant_id.

    Stable across restarts; 80 bits of collision space; fits inside Atlas's
    38-char db-name limit when paired with a sensible DB_NAME.
    """
    if not tenant_id:
        raise ValueError("tenant_id is empty")
    return hashlib.blake2s(tenant_id.encode("utf-8"), digest_size=12).hexdigest()


def tenant_db_name(tenant_id: str) -> str:
    return f"{settings.DB_NAME}_t_{_safe_tenant_suffix(tenant_id)}"


def tenant_db(tenant_id: str) -> AsyncIOMotorDatabase:
    """Return the database handle for `tenant_id`. Caller is responsible for
    ensuring `tenant_id` belongs to the authenticated user."""
    if not tenant_id:
        raise ValueError("tenant_db() requires a tenant_id")
    return get_client()[tenant_db_name(tenant_id)]


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
    # Sanity check — Atlas caps DB names at 38 bytes. Our scheme is
    # `{DB_NAME}_t_<24hex>` = len(DB_NAME) + 27 bytes.
    if len(settings.DB_NAME) + 27 > 38:
        raise RuntimeError(
            f"DB_NAME='{settings.DB_NAME}' is too long for per-tenant naming. "
            f"Max DB_NAME length is 11 chars (got {len(settings.DB_NAME)}). "
            f"Set a shorter DB_NAME in your environment (e.g. 'payroll')."
        )

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

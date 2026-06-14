"""Feature-flag framework — module catalogue + per-employer / per-employee grants.

Concepts
--------
features (global catalog)         — codes like "payroll", "students". Seeded once.
employers.enabled_features        — which modules an employer (client) is sold/granted.
users.feature_permissions         — subset granted by employer to each employee.

Effective access for a user = intersection of their own permissions AND
the employer's enabled list. Revoking at any layer revokes for children.
Super admins implicitly have access to every feature.
"""
from __future__ import annotations

import logging
from typing import Iterable

from ..db import db
from ..utils import gen_id, now_utc

logger = logging.getLogger(__name__)


# Canonical catalog. New modules get added here AND seeded via `seed_features()`.
FEATURE_CATALOG = [
    {
        "code": "payroll",
        "name": "Payroll & Attendance",
        "description": "Mark attendance, apply leaves, generate salary slips.",
        "icon": "Wallet",
        "default_landing_path_by_role": {
            "employer": "/employer",
            "employee": "/me",
            "super_admin": "/admin",
        },
        "is_active": True,
    },
    {
        "code": "students",
        "name": "Student Records",
        "description": "Manage student profiles, documents and Google Sheets sync.",
        "icon": "GraduationCap",
        "default_landing_path_by_role": {
            "employer": "/school",
            "employee": "/school",
            "super_admin": "/school",
        },
        "is_active": True,
    },
]


async def seed_features() -> None:
    """Idempotent feature-catalog seed. Safe to call on every boot."""
    for f in FEATURE_CATALOG:
        existing = await db.features.find_one({"code": f["code"]})
        if existing is None:
            await db.features.insert_one({
                "_id": gen_id(),
                **f,
                "created_at": now_utc(),
                "updated_at": now_utc(),
            })
            logger.info("Seeded feature: %s", f["code"])
        else:
            # Keep description / icon / landing fresh on each deploy. Never
            # touch is_active here — that's an operator decision via admin UI.
            await db.features.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "name": f["name"],
                    "description": f["description"],
                    "icon": f["icon"],
                    "default_landing_path_by_role": f["default_landing_path_by_role"],
                    "updated_at": now_utc(),
                }},
            )


async def backfill_employer_features() -> None:
    """Existing employers (created before this framework) keep only payroll.
    This is an opt-in default — the super admin must explicitly add Students."""
    await db.tenants.update_many(
        {"enabled_features": {"$exists": False}},
        {"$set": {"enabled_features": ["payroll"]}},
    )


async def backfill_user_feature_permissions() -> None:
    """Existing employees and employer-admins implicitly get whatever their
    employer already has enabled — preserves today's behaviour exactly."""
    async for u in db.users.find({"feature_permissions": {"$exists": False}}):
        if u.get("role") == "super_admin":
            # Super admin uses implicit-all; no row stored.
            await db.users.update_one(
                {"_id": u["_id"]}, {"$set": {"feature_permissions": []}}
            )
            continue
        tenant_id = u.get("tenant_id")
        if not tenant_id:
            await db.users.update_one(
                {"_id": u["_id"]}, {"$set": {"feature_permissions": []}}
            )
            continue
        t = await db.tenants.find_one({"_id": tenant_id}, {"enabled_features": 1})
        enabled = (t or {}).get("enabled_features") or ["payroll"]
        await db.users.update_one(
            {"_id": u["_id"]}, {"$set": {"feature_permissions": list(enabled)}}
        )


def _all_feature_codes() -> set[str]:
    return {f["code"] for f in FEATURE_CATALOG}


async def effective_features_for_user(user: dict) -> list[str]:
    """Return the set of feature codes the user can ACTUALLY access right now.

    Super admins implicitly have every active feature (no row needed).
    Everyone else: intersection(user.feature_permissions, employer.enabled_features),
    further intersected with features.is_active=True.
    """
    active_codes = set()
    async for f in db.features.find({"is_active": True}, {"code": 1}):
        active_codes.add(f["code"])

    if user.get("role") == "super_admin":
        return sorted(active_codes)

    tenant_id = user.get("tenant_id")
    if not tenant_id:
        return []

    t = await db.tenants.find_one({"_id": tenant_id}, {"enabled_features": 1})
    employer_enabled = set((t or {}).get("enabled_features") or [])

    user_perms = set(user.get("feature_permissions") or [])
    return sorted(active_codes & employer_enabled & user_perms)


async def features_enabled_for_employer(tenant_id: str) -> list[str]:
    t = await db.tenants.find_one({"_id": tenant_id}, {"enabled_features": 1})
    return list((t or {}).get("enabled_features") or [])


def sanitise_feature_codes(codes: Iterable[str]) -> list[str]:
    """Drop any codes that aren't in the canonical catalog; dedupe; keep order."""
    valid = _all_feature_codes()
    seen, out = set(), []
    for c in codes or []:
        c = (c or "").strip().lower()
        if c in valid and c not in seen:
            seen.add(c)
            out.append(c)
    return out

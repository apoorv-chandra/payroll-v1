"""Idempotent seeders for first boot."""
from __future__ import annotations

import logging

from ..config import settings
from ..db import db
from ..security import hash_password, verify_password
from ..utils import gen_id, gen_signup_code, now_utc

logger = logging.getLogger(__name__)


async def seed_super_admin() -> None:
    existing = await db.users.find_one({"email": settings.ADMIN_EMAIL})
    if existing is None:
        await db.users.insert_one({
            "_id": gen_id(),
            "email": settings.ADMIN_EMAIL,
            "password_hash": hash_password(settings.ADMIN_PASSWORD),
            "name": "Super Admin",
            "role": "super_admin",
            "tenant_id": None,
            "created_at": now_utc(),
        })
        logger.info("Seeded super admin %s", settings.ADMIN_EMAIL)
    elif not verify_password(settings.ADMIN_PASSWORD, existing["password_hash"]):
        await db.users.update_one(
            {"email": settings.ADMIN_EMAIL},
            {"$set": {"password_hash": hash_password(settings.ADMIN_PASSWORD)}},
        )
        logger.info("Refreshed super admin password")


async def seed_platform_settings() -> None:
    """Default platform feature flags (controlled by Super Admin)."""
    defaults = {
        "whatsapp_enabled": False,
        "max_backdate_days": 30,
    }
    for key, value in defaults.items():
        existing = await db.platform_settings.find_one({"key": key})
        if existing is None:
            await db.platform_settings.insert_one({
                "_id": gen_id(),
                "key": key,
                "value": value,
                "updated_at": now_utc(),
            })


async def backfill_signup_codes() -> None:
    """Allocate a signup_code for any legacy tenant that doesn't have one yet."""
    cursor = db.tenants.find({"signup_code": {"$in": [None, ""]}})
    async for t in cursor:
        for _ in range(8):
            candidate = gen_signup_code()
            if not await db.tenants.find_one({"signup_code": candidate}):
                await db.tenants.update_one({"_id": t["_id"]}, {"$set": {"signup_code": candidate}})
                logger.info("Backfilled signup code for tenant %s", t.get("name"))
                break


def default_leave_types() -> list:
    return [
        {"code": "CL", "name": "Casual Leave", "annual_quota": 12, "carry_forward": False, "paid": True},
        {"code": "SL", "name": "Sick Leave", "annual_quota": 8, "carry_forward": True, "paid": True},
        {"code": "OD", "name": "On-Duty", "annual_quota": 0, "carry_forward": False, "paid": True},
        {"code": "HD", "name": "Half-Day", "annual_quota": 0, "carry_forward": False, "paid": True},
        {"code": "CO", "name": "Comp-Off", "annual_quota": 0, "carry_forward": True, "paid": True},
    ]

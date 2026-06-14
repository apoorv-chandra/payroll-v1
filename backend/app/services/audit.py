"""Audit log helper."""
from __future__ import annotations

from typing import Optional

from ..db import employer_db
from ..utils import gen_id, now_utc


async def audit(
    employer_id: Optional[str],
    actor_id: str,
    action: str,
    target: Optional[str] = None,
    meta: Optional[dict] = None,
) -> None:
    if not employer_id:
        # Super-admin actions before any tenant exists are dropped silently —
        # they're already covered by structured logs.
        return
    await employer_db(employer_id).audit_logs.insert_one(
        {
            "_id": gen_id(),
            "employer_id": employer_id,
            "actor_id": actor_id,
            "action": action,
            "target": target,
            "meta": meta or {},
            "created_at": now_utc(),
        }
    )

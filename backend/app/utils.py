"""Generic helpers (id, time, formatting, geo)."""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone, date


def gen_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def today_iso() -> str:
    return date.today().isoformat()


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def indian_fmt(amount) -> str:
    """Format a number with Indian comma grouping (e.g. 1,00,000.00)."""
    try:
        n = float(amount)
    except Exception:
        return str(amount)
    neg = n < 0
    n = abs(n)
    s = f"{n:.2f}"
    integer, dec = s.split(".")
    if len(integer) <= 3:
        formatted = integer
    else:
        last3 = integer[-3:]
        rest = integer[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted = ",".join(groups) + "," + last3
    out = f"{formatted}.{dec}"
    return ("-" + out) if neg else out


def public_user(u: dict | None) -> dict | None:
    if not u:
        return None
    return {
        "id": u["_id"],
        "email": u["email"],
        "name": u.get("name"),
        "role": u["role"],
        "tenant_id": u.get("tenant_id"),
        "employee_id": u.get("employee_id"),
        "elevated_roles": u.get("elevated_roles", []),
        "created_at": u.get("created_at"),
    }


def strip_id(doc: dict) -> dict:
    """Remove Mongo _id / set 'id' for response payloads."""
    if "_id" in doc:
        doc["id"] = doc["_id"]
        return {k: v for k, v in doc.items() if k != "_id"}
    return doc

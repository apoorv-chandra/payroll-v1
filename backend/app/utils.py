"""Generic helpers (id, time, formatting, geo)."""
from __future__ import annotations

import math
import os
import secrets
import uuid
from datetime import datetime, timezone, date, timedelta

try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


# Friendly alphabet — drops 0/O/1/I/L to avoid confusion when read aloud or printed.
SIGNUP_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_SIGNUP_CODE_ALPHABET = SIGNUP_CODE_ALPHABET


# Canonical business timezone for attendance / payroll day boundaries.
# Override with APP_TIMEZONE env if you ever onboard tenants in another region.
APP_TIMEZONE_NAME = os.environ.get("APP_TIMEZONE", "Asia/Kolkata")


def app_tz():
    if ZoneInfo is not None:
        try:
            return ZoneInfo(APP_TIMEZONE_NAME)
        except Exception:
            pass
    # IST fallback if zoneinfo data is missing in the container image.
    return timezone(timedelta(hours=5, minutes=30))


def gen_id() -> str:
    return str(uuid.uuid4())


def gen_signup_code(length: int = 8) -> str:
    """8-char unambiguous alphanumeric code for employer invite links."""
    return "".join(secrets.choice(_SIGNUP_CODE_ALPHABET) for _ in range(length))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def today_iso() -> str:
    """Today's date in the canonical business timezone (Asia/Kolkata by default).

    Avoids using server-local `date.today()` which silently shifts the "work day"
    boundary when the server is running in a different timezone (e.g. UTC on
    Render). A 1 AM IST check-in on Feb 15 should belong to Feb 15, not Feb 14.
    """
    return datetime.now(app_tz()).date().isoformat()


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
        "employer_id": u.get("employer_id"),
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

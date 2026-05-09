"""WhatsApp delivery via Twilio.

Production-ready: drop in TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and
TWILIO_WHATSAPP_FROM in the environment and toggle the global feature
flag from the Super Admin dashboard. Messages fail silently (logged).
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from ..config import settings
from ..db import db

logger = logging.getLogger(__name__)

_PHONE_RE = re.compile(r"[^\d+]")


def normalize_whatsapp(phone: str) -> Optional[str]:
    """Return a Twilio-compatible 'whatsapp:+<digits>' string or None."""
    if not phone:
        return None
    cleaned = _PHONE_RE.sub("", phone)
    if not cleaned.startswith("+"):
        # Assume India (+91) when country code is missing.
        cleaned = "+91" + cleaned.lstrip("0")
    if len(cleaned) < 10:
        return None
    return f"whatsapp:{cleaned}"


async def is_enabled() -> bool:
    """Read the global feature flag set by Super Admin."""
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN):
        return False
    flag = await db.platform_settings.find_one({"key": "whatsapp_enabled"})
    return bool(flag and flag.get("value"))


def _twilio_client():
    from twilio.rest import Client  # local import keeps cold start fast
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


async def send_whatsapp(to_phone: str, body: str) -> Optional[str]:
    if not await is_enabled():
        logger.info("[wa-skip] whatsapp disabled. to=%s", to_phone)
        return None
    to = normalize_whatsapp(to_phone)
    if not to:
        logger.info("[wa-skip] invalid phone=%s", to_phone)
        return None
    try:
        client = _twilio_client()
        msg = await asyncio.to_thread(
            lambda: client.messages.create(
                from_=settings.TWILIO_WHATSAPP_FROM,
                to=to,
                body=body,
            )
        )
        sid = getattr(msg, "sid", None)
        logger.info("[wa-sent] to=%s sid=%s", to, sid)
        return sid
    except Exception as e:
        logger.error("[wa-fail] to=%s err=%s", to, e)
        return None


# ---------- Message templates ----------
def msg_leave_decision(name: str, leave_type: str, frm: str, to: str, decision: str, decided_at_local: str, note: Optional[str] = None) -> str:
    icon = "✅" if decision == "approved" else "❌"
    note_line = f"\nNote: {note}" if note else ""
    return (
        f"Hi {name}, your leave ({leave_type}, {frm} → {to}) has been "
        f"{icon} {decision}.{note_line}\n"
        f"Decided at: {decided_at_local}"
    )


def msg_salary_ready(name: str, month: str, year: int, net: str, approved_at_local: str, app_url: str) -> str:
    return (
        f"Hi {name}, your salary slip for {month} {year} is ready. "
        f"Net payable: ₹ {net}\n"
        f"Approved at: {approved_at_local}\n"
        f"Open the app to download: {app_url}"
    )

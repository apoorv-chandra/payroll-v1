"""Students module — shared helpers and background-tasks.

Pulled out of `routes/students.py` so the route files stay slim (~150 LOC each)
and the Sheets-sync logic has a single home that can be scheduled as a
FastAPI BackgroundTask instead of blocking the request thread.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import HTTPException

from ..db import db, tenant_db
from ..security import sign_file_token
from ..services import sheets as sheets_svc
from ..utils import now_utc, strip_id

logger = logging.getLogger(__name__)


# Public surface — keep in sync with the frontend FILE_SLOTS table.
FILE_SLOTS = [
    "photo", "signature",
    "tenth_marksheet", "twelfth_marksheet",
    "graduation_marksheet", "pg_marksheet",
    "income_certificate", "caste_certificate", "domicile_certificate",
    "affidavit", "aadhaar_front", "aadhaar_back",
]

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB per file

# Editable student fields surfaced via the API (whitelist for PATCH/PUT).
STUDENT_FIELDS = (
    "name", "fathers_name", "mothers_name", "dob", "aadhaar",
    "mobile", "alt_mobile", "email", "category", "gender",
    "address", "city", "state", "pin",
    "tenth_pass_year", "tenth_school", "tenth_board", "tenth_percent",
    "twelfth_pass_year", "twelfth_school", "twelfth_board", "twelfth_percent",
    "grad_percent", "pg_percent", "department", "course", "subjects",
)


# ---------------------------------------------------------------------------
# Privacy helpers
# ---------------------------------------------------------------------------
def mask_aadhaar(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 4:
        return ""
    return "XXXX XXXX " + digits[-4:]


def public_student(student: dict) -> dict:
    """Project a stored student doc into the API shape.

    Aadhaar is masked in responses; raw value never returned. Use a dedicated
    endpoint with re-auth if you ever need to surface the full value (deferred).
    """
    s = strip_id(student)
    if s.get("aadhaar"):
        s["aadhaar_masked"] = mask_aadhaar(s["aadhaar"])
    s.pop("aadhaar", None)
    return s


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------
async def get_student_or_404(tenant_id: str, student_id: str) -> dict:
    tdb = tenant_db(tenant_id)
    s = await tdb.students.find_one({"_id": student_id, "deleted_at": None})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    return s


def can_access(user: dict, student: dict) -> bool:
    if user.get("role") in ("super_admin", "employer"):
        return True
    # Employee can only see students they own.
    return student.get("owner_user_id") == user.get("_id")


# ---------------------------------------------------------------------------
# Signed file URL — embedded in Google Sheets cells
# ---------------------------------------------------------------------------
def signed_file_url(tenant_id: str, file_id: str, base_url: str = "") -> str:
    token = sign_file_token(tenant_id, file_id, ttl_days=30)
    return f"{base_url}/api/students/files/{file_id}?t={token}"


def build_file_links(tenant_id: str, student: dict, base_url: str = "") -> dict[str, str]:
    """Return {slot: signed-download-url} for the Sheets row cell."""
    out: dict[str, str] = {}
    for slot, meta in (student.get("files") or {}).items():
        if not meta or not meta.get("file_id"):
            continue
        out[slot] = signed_file_url(tenant_id, meta["file_id"], base_url)
    return out


# ---------------------------------------------------------------------------
# Google Sheets background sync
# ---------------------------------------------------------------------------
async def sync_to_sheets(user: dict, student: dict, op: str) -> None:
    """Mirror a student CUD operation to the tenant's master Google Sheet.

    Designed for FastAPI's BackgroundTasks — never raises, always logs. Mongo
    is the source of truth; Sheets is a best-effort downstream view.

    The master sheet is PRE-CONFIGURED by the employer (see students_sheets.py
    `configure_master_sheet`). If not configured, sync is silently skipped.
    """
    try:
        if not sheets_svc.is_configured():
            return
        tenant_id = user["tenant_id"]
        tenant = await db.tenants.find_one({"_id": tenant_id})
        if not tenant:
            return
        sheet_id = tenant.get("students_sheet_id")
        if not sheet_id:
            # UI surfaces a banner asking employer to configure; no-op until then.
            return

        # Ensure this teacher (owner) has a dedicated tab on the master sheet.
        teacher_user_id = student.get("owner_user_id")
        teacher_user = await db.users.find_one(
            {"_id": teacher_user_id},
            {"name": 1, "email": 1, "students_sheet_tab": 1},
        )
        if not teacher_user:
            return
        tab = teacher_user.get("students_sheet_tab")
        if not tab:
            try:
                label = (
                    teacher_user.get("name")
                    or (teacher_user.get("email") or "Teacher").split("@")[0]
                )
                tab = await sheets_svc.ensure_teacher_tab(sheet_id, label)
                await db.users.update_one(
                    {"_id": teacher_user_id},
                    {"$set": {"students_sheet_tab": tab}},
                )
            except Exception as e:
                logger.warning("Could not create teacher tab: %s", e)
                return

        # Build the row payload (no base URL in env — sheets cells get
        # relative-to-host links; admins typically view from the same browser
        # session and the Bearer cookie covers them. The `?t=` token is the
        # belt-and-suspenders fallback.)
        file_links = build_file_links(tenant_id, student)

        if op == "create":
            idx = await sheets_svc.safe_append(sheet_id, tab["tab_name"], student, file_links)
            if idx > 0:
                tdb = tenant_db(tenant_id)
                await tdb.students.update_one(
                    {"_id": student["_id"]},
                    {"$set": {"google_sheet_row": idx, "updated_at": now_utc()}},
                )
        elif op == "update":
            idx = student.get("google_sheet_row")
            if idx:
                await sheets_svc.safe_update(
                    sheet_id, tab["tab_name"], idx, student, file_links
                )
            else:
                # Row was missing — append now and remember the index.
                new_idx = await sheets_svc.safe_append(
                    sheet_id, tab["tab_name"], student, file_links
                )
                if new_idx > 0:
                    tdb = tenant_db(tenant_id)
                    await tdb.students.update_one(
                        {"_id": student["_id"]},
                        {"$set": {"google_sheet_row": new_idx}},
                    )
        elif op == "delete":
            idx = student.get("google_sheet_row")
            if idx:
                await sheets_svc.safe_strike(sheet_id, tab["tab_id"], idx)
    except Exception as e:
        # Last-ditch safety net — background tasks shouldn't raise into the
        # event loop.
        logger.exception("sync_to_sheets failed: %s", e)

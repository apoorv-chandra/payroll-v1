"""Google Sheets sync — master spreadsheet per employer, one tab per teacher.

Mirrors `/artifacts/api-server/src/lib/sheets.ts` from the Node port.

Design
------
- One master spreadsheet PER EMPLOYER (tenant). Stored as `tenant.students_sheet_id`.
- One tab/sheet PER TEACHER (employee). Stored as `employee.students_sheet_tab_name`
  and `employee.students_sheet_tab_id` (numeric gid).
- Every student CRUD mirrors to its teacher's tab.
- A summary "Overview" tab on the master shows totals per teacher.
- All Google client calls run in a threadpool because the official client is
  blocking; we keep FastAPI handlers responsive.

Auth
----
Service-account JSON, base64-encoded into env var GOOGLE_SERVICE_ACCOUNT_JSON_B64.
The service-account EMAIL is exposed for sharing instructions.

Tolerance to failure
--------------------
Sheets failures NEVER block student CRUD. The student record is the source of
truth in Mongo; Sheets sync is a best-effort mirror. Failures are logged but
swallowed so the API still returns success. A future "Resync to Sheets" button
can reconcile drift.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Iterable

logger = logging.getLogger(__name__)


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Stable ordering for the 12 file slots — used as both Sheet column names and
# as the lookup keys when building the row.
TEACHER_TAB_FILE_SLOTS = (
    "photo", "signature",
    "tenth_marksheet", "twelfth_marksheet",
    "graduation_marksheet", "pg_marksheet",
    "income_certificate", "caste_certificate", "domicile_certificate",
    "affidavit", "aadhaar_front", "aadhaar_back",
)

# Pretty header label for each slot — title case, no underscores.
_SLOT_HEADER = {
    "photo": "Photo",
    "signature": "Signature",
    "tenth_marksheet": "10th Marksheet",
    "twelfth_marksheet": "12th Marksheet",
    "graduation_marksheet": "Graduation",
    "pg_marksheet": "PG",
    "income_certificate": "Income Cert.",
    "caste_certificate": "Caste Cert.",
    "domicile_certificate": "Domicile Cert.",
    "affidavit": "Affidavit",
    "aadhaar_front": "Aadhaar (Front)",
    "aadhaar_back": "Aadhaar (Back)",
}


# Column header used on each teacher's tab. Order matters — student row writes
# follow this exact order. The 12 trailing columns are one-per-file-slot so
# each upload gets its OWN clickable HYPERLINK cell (joining multiple
# HYPERLINK formulas inside a single cell makes Sheets treat them as plain
# text — they only render as clickable links one-per-cell).
TEACHER_TAB_HEADERS = [
    "Sl. No.",
    "Student Name",
    "Father's Name",
    "Mother's Name",
    "Date of Birth",
    "Aadhaar (Masked)",
    "Mobile",
    "Alt. Mobile",
    "Email",
    "Category",
    "Gender",
    "Address",
    "City",
    "State",
    "Pin",
    "10th %",
    "12th %",
    "Graduation %",
    "PG %",
    "Last Updated",
    *[_SLOT_HEADER[s] for s in TEACHER_TAB_FILE_SLOTS],
]

# Tab name sanitisation — Sheets disallows :, \, /, ?, *, [, ]
_TAB_SAFE = re.compile(r"[:\\/?*\[\]]")


# Single threadpool reused for all Google calls. The official client is blocking
# but very thin around HTTP; 4 workers is enough for our throughput needs.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gsheets")


def is_configured() -> bool:
    """Whether Sheets sync is wired. UIs use this to show a "configure" banner."""
    return bool(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_B64") or
                os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))


@lru_cache(maxsize=1)
def _load_service_account_info() -> dict | None:
    """Decode the service-account JSON from env. Cached for the process life."""
    raw_b64 = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_B64")
    raw_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw_b64:
        try:
            return json.loads(base64.b64decode(raw_b64).decode("utf-8"))
        except Exception as e:
            logger.error("Failed to decode GOOGLE_SERVICE_ACCOUNT_JSON_B64: %s", e)
            return None
    if raw_json:
        try:
            return json.loads(raw_json)
        except Exception as e:
            logger.error("Failed to parse GOOGLE_SERVICE_ACCOUNT_JSON: %s", e)
            return None
    return None


def service_account_email() -> str | None:
    info = _load_service_account_info()
    return (info or {}).get("client_email")


@lru_cache(maxsize=1)
def _sheets_client():
    info = _load_service_account_info()
    if not info:
        return None
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


@lru_cache(maxsize=1)
def _drive_client():
    info = _load_service_account_info()
    if not info:
        return None
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _run(fn, *args, **kwargs):
    """Run a blocking Google call in our threadpool, awaited from async code."""
    return asyncio.get_event_loop().run_in_executor(
        _executor, lambda: fn(*args, **kwargs)
    )


def safe_tab_name(name: str) -> str:
    name = (name or "").strip()
    name = _TAB_SAFE.sub("-", name)
    # Sheets tab names cap at 100 chars.
    return name[:99] or "Teacher"


# ---------------------------------------------------------------------------
# Spreadsheet lifecycle
# ---------------------------------------------------------------------------
async def create_master_spreadsheet(employer_name: str, share_with: list[str] | None = None) -> dict:
    """Create a fresh master spreadsheet with an Overview tab.

    Returns {id, url, overviewTabId}. Caller stores the id on the tenant doc.
    Shares Editor access with the listed emails (typically the employer-admin).
    """
    sheets = _sheets_client()
    drive = _drive_client()
    if not sheets or not drive:
        raise RuntimeError("Google Sheets sync is not configured")

    body = {
        "properties": {"title": f"Students — {employer_name}"},
        "sheets": [{"properties": {"title": "Overview", "gridProperties": {"frozenRowCount": 1}}}],
    }

    def _create():
        resp = sheets.spreadsheets().create(body=body, fields="spreadsheetId,sheets.properties").execute()
        return resp

    resp = await _run(_create)
    spreadsheet_id = resp["spreadsheetId"]
    overview_tab_id = resp["sheets"][0]["properties"]["sheetId"]

    # Write the Overview header
    await _run(
        lambda: sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Overview!A1:C1",
            valueInputOption="USER_ENTERED",
            body={"values": [["Teacher", "Students", "Tab"]]},
        ).execute()
    )

    # Share with employer admins (Editor) so they can view in the browser.
    for email in share_with or []:
        try:
            await _run(
                lambda e=email: drive.permissions().create(
                    fileId=spreadsheet_id,
                    body={"type": "user", "role": "writer", "emailAddress": e},
                    sendNotificationEmail=False,
                ).execute()
            )
        except Exception as e:
            logger.warning("Failed to share sheet with %s: %s", email, e)

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    return {"id": spreadsheet_id, "url": url, "overview_tab_id": overview_tab_id}


async def share_spreadsheet(spreadsheet_id: str, email: str, role: str = "writer") -> None:
    drive = _drive_client()
    if not drive:
        return
    await _run(
        lambda: drive.permissions().create(
            fileId=spreadsheet_id,
            body={"type": "user", "role": role, "emailAddress": email},
            sendNotificationEmail=False,
        ).execute()
    )


# ---------------------------------------------------------------------------
# Per-teacher tab
# ---------------------------------------------------------------------------
async def ensure_teacher_tab(spreadsheet_id: str, teacher_name: str) -> dict:
    """Add a tab for a teacher (idempotent). Returns {tab_id, tab_name, tab_url}."""
    sheets = _sheets_client()
    if not sheets:
        raise RuntimeError("Sheets not configured")
    title = safe_tab_name(teacher_name)

    def _get_meta():
        return sheets.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets.properties").execute()

    meta = await _run(_get_meta)
    for s in meta.get("sheets", []):
        p = s.get("properties", {})
        if p.get("title") == title:
            return {
                "tab_id": p["sheetId"],
                "tab_name": title,
                "tab_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={p['sheetId']}",
            }

    # Doesn't exist — create with header.
    def _add():
        return sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {
                "title": title,
                "gridProperties": {"frozenRowCount": 1},
            }}}]},
        ).execute()

    r = await _run(_add)
    tab_id = r["replies"][0]["addSheet"]["properties"]["sheetId"]

    # Header row
    await _run(
        lambda: sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{title}'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [TEACHER_TAB_HEADERS]},
        ).execute()
    )

    return {
        "tab_id": tab_id,
        "tab_name": title,
        "tab_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={tab_id}",
    }


def _row_from_student(student: dict, file_links: dict[str, str]) -> list[str]:
    """Project a student doc into the row layout the headers expect.

    file_links: { slot_code: download_url } — converted to a single comma-list cell.
    """
    def f(k, default=""):
        v = student.get(k)
        if v in (None, ""):
            return default
        return v

    aadhaar = (f("aadhaar") or "").replace(" ", "")
    aadhaar_masked = ("XXXX XXXX " + aadhaar[-4:]) if len(aadhaar) >= 4 else aadhaar

    files_cells: list[str] = []
    for slot in TEACHER_TAB_FILE_SLOTS:
        url = (file_links or {}).get(slot)
        if url:
            # Escape any double quotes in URLs so the formula stays valid.
            safe_url = url.replace('"', '%22')
            files_cells.append(f'=HYPERLINK("{safe_url}", "View")')
        else:
            files_cells.append("")

    return [
        f("serial_no"),
        f("name"),
        f("fathers_name"),
        f("mothers_name"),
        f("dob"),
        aadhaar_masked,
        f("mobile"),
        f("alt_mobile"),
        f("email"),
        f("category"),
        f("gender"),
        f("address"),
        f("city"),
        f("state"),
        f("pin"),
        f("tenth_percent"),
        f("twelfth_percent"),
        f("grad_percent"),
        f("pg_percent"),
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        *files_cells,
    ]


async def append_student_row(
    spreadsheet_id: str, tab_name: str, student: dict, file_links: dict[str, str]
) -> int:
    """Append a student row; returns the 1-based row index in the tab."""
    sheets = _sheets_client()
    if not sheets:
        raise RuntimeError("Sheets not configured")
    row = _row_from_student(student, file_links)

    def _append():
        r = sheets.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        # updates.updatedRange like "Sheet1!A5:U5" — parse the row number.
        rng = r.get("updates", {}).get("updatedRange", "")
        m = re.search(r"!A(\d+)", rng)
        return int(m.group(1)) if m else -1

    return await _run(_append)


async def update_student_row(
    spreadsheet_id: str, tab_name: str, row_index: int, student: dict, file_links: dict[str, str]
) -> None:
    sheets = _sheets_client()
    if not sheets:
        raise RuntimeError("Sheets not configured")
    row = _row_from_student(student, file_links)
    await _run(
        lambda: sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!A{row_index}",
            valueInputOption="USER_ENTERED",
            body={"values": [row]},
        ).execute()
    )


async def strike_student_row(spreadsheet_id: str, tab_id: int, row_index: int) -> None:
    """Apply strikethrough formatting to the deleted student's row (soft-delete)."""
    sheets = _sheets_client()
    if not sheets:
        raise RuntimeError("Sheets not configured")
    await _run(
        lambda: sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"repeatCell": {
                "range": {
                    "sheetId": tab_id,
                    "startRowIndex": row_index - 1,
                    "endRowIndex": row_index,
                },
                "cell": {"userEnteredFormat": {"textFormat": {"strikethrough": True}}},
                "fields": "userEnteredFormat.textFormat.strikethrough",
            }}]},
        ).execute()
    )


# ---------------------------------------------------------------------------
# Best-effort wrappers — never raise, always log.
# ---------------------------------------------------------------------------
async def safe_append(spreadsheet_id, tab_name, student, file_links) -> int:
    try:
        return await append_student_row(spreadsheet_id, tab_name, student, file_links)
    except Exception as e:
        logger.warning("Sheets append failed (sheet=%s, tab=%s): %s", spreadsheet_id, tab_name, e)
        return -1


async def safe_update(spreadsheet_id, tab_name, row_index, student, file_links) -> bool:
    try:
        await update_student_row(spreadsheet_id, tab_name, row_index, student, file_links)
        return True
    except Exception as e:
        logger.warning("Sheets update failed: %s", e)
        return False


async def safe_strike(spreadsheet_id, tab_id, row_index) -> bool:
    try:
        await strike_student_row(spreadsheet_id, tab_id, row_index)
        return True
    except Exception as e:
        logger.warning("Sheets strike failed: %s", e)
        return False

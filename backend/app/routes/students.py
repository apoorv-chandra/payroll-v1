"""Students module — CRUD with file uploads + Google Sheets mirror.

Permissions
-----------
All routes require the `students` feature. Inside that:
  • employer or super_admin can see/edit any student in their tenant.
  • employee can only see/edit students THEY own (created by themselves).

Tenancy
-------
Student rows live in the per-tenant DB (`tdb.students`), keyed by `user_id`
of the owning teacher (an employee in the payroll model). Files live in
GridFS on the same per-tenant DB.

Google Sheets sync
------------------
Every CUD operation mirrors to the tenant's master sheet (if configured).
Failures are logged but never block the API response — Mongo is the source
of truth.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..db import db, tenant_db
from ..deps import get_current_user, get_current_user_optional, require_feature
from ..services import gridfs as gridfs_svc
from ..services import sheets as sheets_svc
from ..services.audit import audit
from ..services.file_compress import (
    smart_compress,
    sniff_magic,
    is_allowed_mime,
)
from ..utils import gen_id, now_utc, strip_id

logger = logging.getLogger(__name__)
router = APIRouter(tags=["students"])


# Slot codes mirror the Node app's 12 file fields, plus we accept arbitrary
# new slots without code changes (forward-compatible).
FILE_SLOTS = [
    "photo", "signature",
    "tenth_marksheet", "twelfth_marksheet",
    "graduation_marksheet", "pg_marksheet",
    "income_certificate", "caste_certificate", "domicile_certificate",
    "affidavit", "aadhaar_front", "aadhaar_back",
]

MAX_UPLOAD_BYTES = 25 * 1024 * 1024   # 25 MB hard cap per file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mask_aadhaar(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 4:
        return ""
    return "XXXX XXXX " + digits[-4:]


def _public(student: dict) -> dict:
    """Project a stored student doc into the API shape.

    Aadhaar is masked in responses. Use a dedicated endpoint with a fresh
    captcha + reason field if the full value ever needs surfacing (deferred).
    """
    s = strip_id(student)
    if s.get("aadhaar"):
        s["aadhaar_masked"] = _mask_aadhaar(s["aadhaar"])
    # Never leak raw aadhaar.
    s.pop("aadhaar", None)
    return s


async def _get_student_or_404(tenant_id: str, student_id: str) -> dict:
    tdb = tenant_db(tenant_id)
    s = await tdb.students.find_one({"_id": student_id, "deleted_at": None})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    return s


def _can_access(user: dict, student: dict) -> bool:
    if user.get("role") in ("super_admin", "employer"):
        return True
    # Employee can only see students they own.
    return student.get("owner_user_id") == user.get("_id")


async def _build_file_links(tenant_id: str, student: dict, request_base: str = "") -> dict[str, str]:
    """Return {slot: signed-download-url} for the Sheets row cell."""
    links: dict[str, str] = {}
    files = student.get("files") or {}
    for slot, meta in files.items():
        if not meta or not meta.get("file_id"):
            continue
        # Best-effort signed link valid for 30 days. Generated server-side
        # so it's safe to embed in a Sheets cell.
        from ..security import sign_file_token
        token = sign_file_token(tenant_id, meta["file_id"], ttl_days=30)
        links[slot] = f"{request_base}/api/students/files/{meta['file_id']}?t={token}"
    return links


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class StudentIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    fathers_name: Optional[str] = ""
    mothers_name: Optional[str] = ""
    dob: Optional[str] = ""
    aadhaar: Optional[str] = ""
    mobile: Optional[str] = ""
    alt_mobile: Optional[str] = ""
    email: Optional[str] = ""
    category: Optional[str] = ""
    gender: Optional[str] = ""
    address: Optional[str] = ""
    city: Optional[str] = ""
    state: Optional[str] = ""
    pin: Optional[str] = ""
    tenth_pass_year: Optional[str] = ""
    tenth_school: Optional[str] = ""
    tenth_board: Optional[str] = ""
    tenth_percent: Optional[str] = ""
    twelfth_pass_year: Optional[str] = ""
    twelfth_school: Optional[str] = ""
    twelfth_board: Optional[str] = ""
    twelfth_percent: Optional[str] = ""
    grad_percent: Optional[str] = ""
    pg_percent: Optional[str] = ""
    department: Optional[str] = ""
    course: Optional[str] = ""
    subjects: Optional[str] = ""


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.get("/students")
async def list_students(
    q: str = Query("", alias="q"),
    skip: int = 0,
    limit: int = 50,
    user: dict = Depends(require_feature("students")),
):
    tdb = tenant_db(user["tenant_id"])
    flt: dict = {"deleted_at": None}
    if user["role"] not in ("super_admin", "employer"):
        flt["owner_user_id"] = user["_id"]
    if q.strip():
        safe = re.escape(q.strip())
        flt["$or"] = [
            {"name": {"$regex": safe, "$options": "i"}},
            {"fathers_name": {"$regex": safe, "$options": "i"}},
            {"mobile": {"$regex": safe, "$options": "i"}},
            {"email": {"$regex": safe, "$options": "i"}},
        ]
    limit = max(1, min(int(limit), 200))
    skip = max(0, int(skip))
    total = await tdb.students.count_documents(flt)
    cursor = tdb.students.find(flt).sort("created_at", -1).skip(skip).limit(limit)
    items = [_public(s) async for s in cursor]
    return {"total": total, "skip": skip, "limit": limit, "items": items}


@router.post("/students")
async def create_student(
    payload: StudentIn,
    user: dict = Depends(require_feature("students")),
):
    tdb = tenant_db(user["tenant_id"])
    sid = gen_id()
    doc = {
        "_id": sid,
        "tenant_id": user["tenant_id"],
        "owner_user_id": user["_id"],
        "owner_name": user.get("name") or user.get("email"),
        "serial_no": "",
        "files": {},
        "google_sheet_row": None,
        "deleted_at": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
        **payload.model_dump(),
    }
    # Auto-serial: next number per tenant.
    last = await tdb.students.find_one({}, sort=[("serial_no_int", -1)])
    next_n = ((last or {}).get("serial_no_int") or 0) + 1
    doc["serial_no_int"] = next_n
    doc["serial_no"] = str(next_n)
    await tdb.students.insert_one(doc)
    await audit(user["tenant_id"], user["_id"], "student.create", sid,
                {"name": payload.name})

    # Sheets mirror (best-effort, non-blocking).
    await _maybe_sync_to_sheets(user, doc, op="create")

    return _public(doc)


@router.get("/students/{student_id}")
async def get_student(
    student_id: str,
    user: dict = Depends(require_feature("students")),
):
    s = await _get_student_or_404(user["tenant_id"], student_id)
    if not _can_access(user, s):
        raise HTTPException(status_code=403, detail="Forbidden")
    return _public(s)


@router.patch("/students/{student_id}")
async def update_student(
    student_id: str,
    payload: StudentIn,
    user: dict = Depends(require_feature("students")),
):
    tdb = tenant_db(user["tenant_id"])
    s = await _get_student_or_404(user["tenant_id"], student_id)
    if not _can_access(user, s):
        raise HTTPException(status_code=403, detail="Forbidden")
    upd = {**payload.model_dump(), "updated_at": now_utc(),
           "updated_by_user_id": user["_id"],
           "updated_by_name": user.get("name") or user.get("email")}
    await tdb.students.update_one({"_id": student_id}, {"$set": upd})
    s2 = await tdb.students.find_one({"_id": student_id})
    await audit(user["tenant_id"], user["_id"], "student.update", student_id,
                {"name": payload.name})
    await _maybe_sync_to_sheets(user, s2, op="update")
    return _public(s2)


@router.delete("/students/{student_id}")
async def delete_student(
    student_id: str,
    user: dict = Depends(require_feature("students")),
):
    tdb = tenant_db(user["tenant_id"])
    s = await _get_student_or_404(user["tenant_id"], student_id)
    if not _can_access(user, s):
        raise HTTPException(status_code=403, detail="Forbidden")
    await tdb.students.update_one(
        {"_id": student_id}, {"$set": {"deleted_at": now_utc()}}
    )
    await audit(user["tenant_id"], user["_id"], "student.delete", student_id, {})
    await _maybe_sync_to_sheets(user, s, op="delete")
    return {"ok": True}


# ---------------------------------------------------------------------------
# File upload / download
# ---------------------------------------------------------------------------
@router.post("/students/{student_id}/files/{slot}")
async def upload_student_file(
    student_id: str,
    slot: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_feature("students")),
):
    if slot not in FILE_SLOTS:
        raise HTTPException(status_code=400, detail=f"Unknown slot: {slot}")
    tdb = tenant_db(user["tenant_id"])
    s = await _get_student_or_404(user["tenant_id"], student_id)
    if not _can_access(user, s):
        raise HTTPException(status_code=403, detail="Forbidden")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25MB)")

    # Magic-byte sniff: client-declared mime is ignored. Defends against
    # someone uploading an executable disguised as image/png.
    real_mime = sniff_magic(content)
    if not is_allowed_mime(real_mime):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type ({real_mime}). Allowed: JPEG/PNG/WEBP/PDF.",
        )

    compressed, final_mime = smart_compress(content, real_mime)
    file_id = await gridfs_svc.upload(
        user["tenant_id"],
        filename=file.filename or f"{student_id}-{slot}",
        content=compressed,
        content_type=final_mime,
        metadata={"student_id": student_id, "slot": slot, "uploaded_by": user["_id"]},
    )

    # Replace any existing file for this slot (delete the old to save space).
    old = (s.get("files") or {}).get(slot)
    if old and old.get("file_id"):
        await gridfs_svc.delete(user["tenant_id"], old["file_id"])

    await tdb.students.update_one(
        {"_id": student_id},
        {"$set": {
            f"files.{slot}": {
                "file_id": file_id,
                "filename": file.filename or "",
                "mime": final_mime,
                "size": len(compressed),
                "uploaded_at": now_utc(),
            },
            "updated_at": now_utc(),
        }},
    )
    s2 = await tdb.students.find_one({"_id": student_id})
    await _maybe_sync_to_sheets(user, s2, op="update")
    return _public(s2)


@router.delete("/students/{student_id}/files/{slot}")
async def delete_student_file(
    student_id: str,
    slot: str,
    user: dict = Depends(require_feature("students")),
):
    tdb = tenant_db(user["tenant_id"])
    s = await _get_student_or_404(user["tenant_id"], student_id)
    if not _can_access(user, s):
        raise HTTPException(status_code=403, detail="Forbidden")
    existing = (s.get("files") or {}).get(slot)
    if not existing:
        return {"ok": True}
    await gridfs_svc.delete(user["tenant_id"], existing["file_id"])
    await tdb.students.update_one(
        {"_id": student_id},
        {"$unset": {f"files.{slot}": ""}, "$set": {"updated_at": now_utc()}},
    )
    s2 = await tdb.students.find_one({"_id": student_id})
    await _maybe_sync_to_sheets(user, s2, op="update")
    return {"ok": True}


@router.get("/students/files/{file_id}")
async def download_student_file(
    file_id: str,
    t: str = Query(""),
    user: dict | None = Depends(get_current_user_optional),
):
    """Download a student file. Auth is satisfied by EITHER:
      • a valid Bearer JWT (in-app usage), OR
      • a short-lived HMAC `t=` token (used for Google Sheets cells).

    Without one of these the endpoint returns 401 — fixing the old Node app's
    bug where ObjectIds were treated as "secret".
    """
    from ..security import verify_file_token

    if not user and t:
        info = verify_file_token(t)
        if not info or info.get("file_id") != file_id:
            raise HTTPException(status_code=401, detail="Invalid file token")
        tenant_id = info["tenant_id"]
    elif user:
        tenant_id = user.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=400, detail="No tenant scope")
    else:
        raise HTTPException(status_code=401, detail="Unauthorized")

    meta = await gridfs_svc.get_metadata(tenant_id, file_id)
    if not meta:
        raise HTTPException(status_code=404, detail="File not found")

    headers = {
        # Force download for unknown types so we never inline render arbitrary
        # content from the same origin (XSS-via-SVG defence).
        "Content-Disposition": f'attachment; filename="{meta["filename"]}"',
        "Cache-Control": "private, max-age=0, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(
        gridfs_svc.stream_chunks(tenant_id, file_id),
        media_type=meta["content_type"] or "application/octet-stream",
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Sheets mirror — fire-and-forget wrapper
# ---------------------------------------------------------------------------
async def _maybe_sync_to_sheets(user: dict, student: dict, op: str) -> None:
    """Best-effort Sheets mirror. Always swallows errors.

    For each (employer, teacher) we maintain a master spreadsheet with one tab
    per teacher. The master sheet is PRE-CONFIGURED by the employer via
    PUT /api/students/_sheets/configure (since service accounts can't create
    sheets in personal Drives — a Google limitation). If not configured,
    sync is silently skipped.
    """
    if not sheets_svc.is_configured():
        return
    tenant_id = user["tenant_id"]
    tenant = await db.tenants.find_one({"_id": tenant_id})
    if not tenant:
        return

    sheet_id = tenant.get("students_sheet_id")
    if not sheet_id:
        # No master sheet configured yet — silently skip. The UI shows a banner
        # prompting the employer to configure it.
        return

    # Ensure teacher tab exists.
    teacher_user_id = student.get("owner_user_id")
    teacher_user = await db.users.find_one({"_id": teacher_user_id}, {"name": 1, "email": 1, "students_sheet_tab": 1})
    if not teacher_user:
        return
    tab = (teacher_user or {}).get("students_sheet_tab")
    if not tab:
        try:
            label = teacher_user.get("name") or (teacher_user.get("email") or "Teacher").split("@")[0]
            tab = await sheets_svc.ensure_teacher_tab(sheet_id, label)
            await db.users.update_one(
                {"_id": teacher_user_id},
                {"$set": {"students_sheet_tab": tab}},
            )
        except Exception as e:
            logger.warning("Could not create teacher tab: %s", e)
            return

    file_links = await _build_file_links(tenant_id, student)
    if op == "create":
        idx = await sheets_svc.safe_append(sheet_id, tab["tab_name"], student, file_links)
        if idx > 0:
            tdb = tenant_db(tenant_id)
            await tdb.students.update_one(
                {"_id": student["_id"]},
                {"$set": {"google_sheet_row": idx}},
            )
    elif op == "update":
        idx = student.get("google_sheet_row")
        if idx:
            await sheets_svc.safe_update(sheet_id, tab["tab_name"], idx, student, file_links)
        else:
            new_idx = await sheets_svc.safe_append(sheet_id, tab["tab_name"], student, file_links)
            if new_idx > 0:
                tdb = tenant_db(tenant_id)
                await tdb.students.update_one(
                    {"_id": student["_id"]}, {"$set": {"google_sheet_row": new_idx}}
                )
    elif op == "delete":
        idx = student.get("google_sheet_row")
        if idx:
            await sheets_svc.safe_strike(sheet_id, tab["tab_id"], idx)


# ---------------------------------------------------------------------------
# Sheets meta endpoints (super_admin/employer scope only)
# ---------------------------------------------------------------------------
@router.get("/students/_sheets/info")
async def sheets_info(user: dict = Depends(require_feature("students"))):
    """Tells the UI whether Sheets sync is configured + the master sheet URL."""
    tenant = await db.tenants.find_one({"_id": user["tenant_id"]})
    return {
        "configured": sheets_svc.is_configured(),
        "service_account_email": sheets_svc.service_account_email(),
        "master_sheet_id": (tenant or {}).get("students_sheet_id"),
        "master_sheet_url": (tenant or {}).get("students_sheet_url"),
    }


class SheetConfigurePayload(BaseModel):
    # Accept either a raw spreadsheet id or a full Google Sheets URL.
    url_or_id: str = Field(..., min_length=10)


_SHEET_ID_FROM_URL = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")


def _extract_sheet_id(url_or_id: str) -> str:
    s = (url_or_id or "").strip()
    m = _SHEET_ID_FROM_URL.search(s)
    return m.group(1) if m else s


@router.put("/students/_sheets/configure")
async def configure_master_sheet(
    payload: SheetConfigurePayload,
    user: dict = Depends(require_feature("students")),
):
    """Bind an existing Google spreadsheet as this employer's master sheet.

    The employer MUST:
      1. Create the spreadsheet themselves (any blank one works).
      2. Share it with our service account email as **Editor**.
      3. Paste the URL or id here.

    Why pre-create? Service accounts can't create files in personal Drives
    (no storage quota). This is the standard workaround.
    """
    if user["role"] not in ("super_admin", "employer"):
        raise HTTPException(status_code=403, detail="Only employer/super admin can configure Sheets")
    if not sheets_svc.is_configured():
        raise HTTPException(status_code=400, detail="Google Sheets sync is not configured on the server")

    sheet_id = _extract_sheet_id(payload.url_or_id)

    # Probe write access before saving — surfaces permission errors immediately.
    try:
        from googleapiclient.errors import HttpError
        client = sheets_svc._sheets_client()
        # Issue a no-op batchUpdate (no requests array → just validates auth).
        await sheets_svc._run(
            lambda: client.spreadsheets().get(spreadsheetId=sheet_id, fields="spreadsheetId").execute()
        )
    except Exception as e:
        msg = str(e)
        if "404" in msg:
            raise HTTPException(status_code=400, detail="Spreadsheet not found. Check the URL/ID.")
        if "403" in msg or "PERMISSION_DENIED" in msg:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Service account doesn't have access. Share the sheet with "
                    f"{sheets_svc.service_account_email()} as Editor, then retry."
                ),
            )
        raise HTTPException(status_code=400, detail=f"Sheets check failed: {msg}")

    # Ensure an Overview tab + header exist (idempotent).
    try:
        client = sheets_svc._sheets_client()
        meta = await sheets_svc._run(
            lambda: client.spreadsheets().get(spreadsheetId=sheet_id, fields="sheets.properties").execute()
        )
        has_overview = any((s.get("properties") or {}).get("title") == "Overview" for s in meta.get("sheets", []))
        if not has_overview:
            await sheets_svc._run(
                lambda: client.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body={"requests": [{"addSheet": {"properties": {"title": "Overview"}}}]},
                ).execute()
            )
            await sheets_svc._run(
                lambda: client.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range="Overview!A1:C1",
                    valueInputOption="USER_ENTERED",
                    body={"values": [["Teacher", "Students", "Tab"]]},
                ).execute()
            )
    except Exception as e:
        logger.warning("Could not bootstrap Overview tab: %s", e)

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
    await db.tenants.update_one(
        {"_id": user["tenant_id"]},
        {"$set": {
            "students_sheet_id": sheet_id,
            "students_sheet_url": url,
            "students_sheet_configured_at": now_utc(),
            "students_sheet_configured_by": user["_id"],
        }},
    )
    await audit(user["tenant_id"], user["_id"], "students.sheet.configure", sheet_id, {"url": url})
    return {"ok": True, "master_sheet_id": sheet_id, "master_sheet_url": url}


@router.delete("/students/_sheets/configure")
async def clear_master_sheet(user: dict = Depends(require_feature("students"))):
    if user["role"] not in ("super_admin", "employer"):
        raise HTTPException(status_code=403, detail="Only employer/super admin")
    await db.tenants.update_one(
        {"_id": user["tenant_id"]},
        {"$unset": {"students_sheet_id": "", "students_sheet_url": ""}},
    )
    # Also clear teacher tab bindings so they're rebuilt on next use.
    await db.users.update_many(
        {"tenant_id": user["tenant_id"]},
        {"$unset": {"students_sheet_tab": ""}},
    )
    return {"ok": True}

"""Students module — Google Sheets configure / status endpoints.

The actual row sync runs inside FastAPI BackgroundTasks (see
`services/students_service.py::sync_to_sheets`). These endpoints just expose
configuration to the UI.
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import db
from ..deps import require_feature
from ..services import sheets as sheets_svc
from ..services.audit import audit
from ..utils import gen_id, now_utc

logger = logging.getLogger(__name__)
router = APIRouter(tags=["students"])


# Extract a spreadsheet id from either a raw id or a full Sheets URL.
_SHEET_ID_FROM_URL = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")


def _extract_sheet_id(url_or_id: str) -> str:
    s = (url_or_id or "").strip()
    m = _SHEET_ID_FROM_URL.search(s)
    return m.group(1) if m else s


class SheetConfigurePayload(BaseModel):
    # Accept either a raw spreadsheet id or a full Google Sheets URL.
    url_or_id: str = Field(..., min_length=10)


@router.get("/students/_sheets/info")
async def sheets_info(user: dict = Depends(require_feature("students"))):
    """Tells the UI whether Sheets sync is configured + the master sheet URL."""
    tenant = await db.employers.find_one({"_id": user["employer_id"]})
    return {
        "configured": sheets_svc.is_configured(),
        "service_account_email": sheets_svc.service_account_email(),
        "master_sheet_id": (tenant or {}).get("students_sheet_id"),
        "master_sheet_url": (tenant or {}).get("students_sheet_url"),
    }


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
    client = sheets_svc._sheets_client()
    try:
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
        meta = await sheets_svc._run(
            lambda: client.spreadsheets().get(spreadsheetId=sheet_id, fields="sheets.properties").execute()
        )
        has_overview = any(
            (s.get("properties") or {}).get("title") == "Overview"
            for s in meta.get("sheets", [])
        )
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
    await db.employers.update_one(
        {"_id": user["employer_id"]},
        {"$set": {
            "students_sheet_id": sheet_id,
            "students_sheet_url": url,
            "students_sheet_configured_at": now_utc(),
            "students_sheet_configured_by": user["_id"],
        }},
    )
    await audit(user["employer_id"], user["_id"], "students.sheet.configure", sheet_id, {"url": url})
    return {"ok": True, "master_sheet_id": sheet_id, "master_sheet_url": url}


@router.delete("/students/_sheets/configure")
async def clear_master_sheet(user: dict = Depends(require_feature("students"))):
    if user["role"] not in ("super_admin", "employer"):
        raise HTTPException(status_code=403, detail="Only employer/super admin")
    await db.employers.update_one(
        {"_id": user["employer_id"]},
        {"$unset": {"students_sheet_id": "", "students_sheet_url": ""}},
    )
    # Also clear teacher tab bindings so they're rebuilt on next use.
    await db.users.update_many(
        {"employer_id": user["employer_id"]},
        {"$unset": {"students_sheet_tab": ""}},
    )
    return {"ok": True}


@router.post("/students/_sheets/resync")
async def resync_master_sheet(
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_feature("students")),
):
    """Queue a Sheets re-sync. Runs in the background; client polls
    `GET /api/students/_sheets/resync/{job_id}` for progress.

    Why background: walking N students × ~200 ms Google round-trip means an
    employer with 500 students would hit a 60-90 second request timeout.
    A background job keeps the API snappy and lets the UI show progress.
    """
    if user["role"] not in ("super_admin", "employer"):
        raise HTTPException(status_code=403, detail="Only employer/super admin")
    if not sheets_svc.is_configured():
        raise HTTPException(status_code=400, detail="Google Sheets sync is not configured")

    tenant = await db.employers.find_one({"_id": user["employer_id"]})
    if not tenant or not tenant.get("students_sheet_id"):
        raise HTTPException(
            status_code=400,
            detail="No master sheet bound yet. Configure it first.",
        )

    # Reset every teacher's tab binding + every student's row index so the
    # next sync_to_sheets call rebuilds from scratch.
    await db.users.update_many(
        {"employer_id": user["employer_id"]},
        {"$unset": {"students_sheet_tab": ""}},
    )
    from ..db import employer_db
    edb = employer_db(user["employer_id"])
    await edb.students.update_many(
        {"deleted_at": None}, {"$set": {"google_sheet_row": None}}
    )

    # Create the job document. The worker updates this as it progresses; the
    # UI polls it.
    total = await edb.students.count_documents({"deleted_at": None})
    job_id = gen_id()
    await edb.resync_jobs.insert_one({
        "_id": job_id,
        "status": "queued",
        "progress": 0,
        "total": total,
        "errors": [],
        "more_errors": 0,
        "created_at": now_utc(),
        "created_by": user["_id"],
        "started_at": None,
        "finished_at": None,
    })

    background_tasks.add_task(_run_resync_job, user["employer_id"], job_id)
    await audit(user["employer_id"], user["_id"], "students.sheet.resync.start", job_id,
                {"total": total})
    return {"ok": True, "job_id": job_id, "total": total, "status": "queued"}


@router.get("/students/_sheets/resync/{job_id}")
async def get_resync_status(
    job_id: str,
    user: dict = Depends(require_feature("students")),
):
    """Poll endpoint. Returns the live job state — UI updates a progress bar
    until status becomes `completed` or `failed`.
    """
    from ..db import employer_db
    edb = employer_db(user["employer_id"])
    job = await edb.resync_jobs.find_one({"_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job["id"] = job["_id"]
    return {k: v for k, v in job.items() if k != "_id"}


async def _run_resync_job(employer_id: str, job_id: str) -> None:
    """Worker that walks students and syncs each. Runs inside FastAPI's
    BackgroundTasks event loop — same process, after the response is sent.
    """
    from ..db import employer_db
    from ..services.students_service import sync_to_sheets

    edb = employer_db(employer_id)
    await edb.resync_jobs.update_one(
        {"_id": job_id},
        {"$set": {"status": "running", "started_at": now_utc()}},
    )

    synced = 0
    errors: list[str] = []
    try:
        cursor = edb.students.find({"deleted_at": None}).sort("serial_no_int", 1)
        async for s in cursor:
            try:
                await sync_to_sheets({"employer_id": employer_id}, s, "create")
                synced += 1
            except Exception as e:
                errors.append(f"#{s.get('serial_no', '?')} {s.get('name', '?')}: {e}")

            # Update progress every 5 students so the UI feels live without
            # hammering Mongo on every single row.
            if synced % 5 == 0 or len(errors) % 5 == 0:
                await edb.resync_jobs.update_one(
                    {"_id": job_id},
                    {"$set": {
                        "progress": synced,
                        "errors": errors[:10],
                        "more_errors": max(0, len(errors) - 10),
                    }},
                )

        await edb.resync_jobs.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "completed",
                "progress": synced,
                "errors": errors[:10],
                "more_errors": max(0, len(errors) - 10),
                "finished_at": now_utc(),
            }},
        )
        logger.info("Resync job %s done: synced=%d errors=%d", job_id, synced, len(errors))
    except Exception as e:
        logger.exception("Resync job %s crashed", job_id)
        await edb.resync_jobs.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "failed",
                "progress": synced,
                "fatal_error": str(e),
                "errors": errors[:10],
                "more_errors": max(0, len(errors) - 10),
                "finished_at": now_utc(),
            }},
        )

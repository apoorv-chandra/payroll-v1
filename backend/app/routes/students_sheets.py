"""Students module — Google Sheets configure / status endpoints.

The actual row sync runs inside FastAPI BackgroundTasks (see
`services/students_service.py::sync_to_sheets`). These endpoints just expose
configuration to the UI.
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import db
from ..deps import require_feature
from ..services import sheets as sheets_svc
from ..services.audit import audit
from ..utils import now_utc

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
    tenant = await db.tenants.find_one({"_id": user["tenant_id"]})
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

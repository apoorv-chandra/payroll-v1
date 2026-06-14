"""Students files — upload, download, delete via GridFS.

Download supports BOTH a Bearer JWT (in-app usage) and a signed `?t=` token
(for Google Sheets cells). This is what fixes the original Node app's
"ObjectIds are unguessable" anti-pattern.
"""
from __future__ import annotations

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile,
)
from fastapi.responses import StreamingResponse

from ..db import tenant_db
from ..deps import get_current_user_optional, require_feature
from ..security import verify_file_token
from ..services import gridfs as gridfs_svc
from ..services.file_compress import (
    is_allowed_mime,
    smart_compress,
    sniff_magic,
)
from ..services.students_service import (
    FILE_SLOTS,
    MAX_UPLOAD_BYTES,
    can_access,
    get_student_or_404,
    public_student,
    sync_to_sheets,
)
from ..utils import now_utc

router = APIRouter(tags=["students"])


@router.post("/students/{student_id}/files/{slot}")
async def upload_student_file(
    student_id: str,
    slot: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(require_feature("students")),
):
    if slot not in FILE_SLOTS:
        raise HTTPException(status_code=400, detail=f"Unknown slot: {slot}")
    tdb = tenant_db(user["tenant_id"])
    s = await get_student_or_404(user["tenant_id"], student_id)
    if not can_access(user, s):
        raise HTTPException(status_code=403, detail="Forbidden")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25MB)")

    # Magic-byte sniff: client-declared MIME is ignored. Defends against
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

    # Replace any existing file for this slot — delete the old to save space.
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
    background_tasks.add_task(sync_to_sheets, user, s2, "update")
    return public_student(s2)


@router.delete("/students/{student_id}/files/{slot}")
async def delete_student_file(
    student_id: str,
    slot: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_feature("students")),
):
    tdb = tenant_db(user["tenant_id"])
    s = await get_student_or_404(user["tenant_id"], student_id)
    if not can_access(user, s):
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
    background_tasks.add_task(sync_to_sheets, user, s2, "update")
    return {"ok": True}


@router.get("/students/files/{file_id}")
async def download_student_file(
    file_id: str,
    t: str = Query(""),
    user: dict | None = Depends(get_current_user_optional),
):
    """Download a student file. Auth is satisfied by EITHER:
      * a valid Bearer JWT (in-app usage), OR
      * a short-lived HMAC `t=` token (used for Google Sheets cells).

    Without one of these the endpoint returns 401 — fixing the original
    Node app's bug where ObjectIds were treated as 'secret'.
    """
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
        # Force download for unknown types so we never inline-render arbitrary
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

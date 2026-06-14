"""Students CRUD — list, create, get, patch, soft-delete.

File upload/download lives in `students_files.py`. Google Sheets sync
configuration lives in `students_sheets.py`.
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import tenant_db
from ..deps import require_feature
from ..services.audit import audit
from ..services.students_service import (
    can_access,
    get_student_or_404,
    public_student,
    sync_to_sheets,
)
from ..utils import gen_id, now_utc

router = APIRouter(tags=["students"])


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
    items = [public_student(s) async for s in cursor]
    return {"total": total, "skip": skip, "limit": limit, "items": items}


@router.post("/students")
async def create_student(
    payload: StudentIn,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_feature("students")),
):
    tdb = tenant_db(user["tenant_id"])
    sid = gen_id()
    # Auto-serial: next number per tenant. Race-free as long as MongoDB
    # processes inserts serially in the same shard — good enough for our scale.
    last = await tdb.students.find_one({}, sort=[("serial_no_int", -1)])
    next_n = ((last or {}).get("serial_no_int") or 0) + 1
    doc = {
        "_id": sid,
        "tenant_id": user["tenant_id"],
        "owner_user_id": user["_id"],
        "owner_name": user.get("name") or user.get("email"),
        "serial_no_int": next_n,
        "serial_no": str(next_n),
        "files": {},
        "google_sheet_row": None,
        "deleted_at": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
        **payload.model_dump(),
    }
    await tdb.students.insert_one(doc)
    await audit(user["tenant_id"], user["_id"], "student.create", sid, {"name": payload.name})

    # Sheets sync runs in the background — never blocks the API response.
    background_tasks.add_task(sync_to_sheets, user, doc, "create")
    return public_student(doc)


@router.get("/students/{student_id}")
async def get_student(
    student_id: str,
    user: dict = Depends(require_feature("students")),
):
    s = await get_student_or_404(user["tenant_id"], student_id)
    if not can_access(user, s):
        raise HTTPException(status_code=403, detail="Forbidden")
    return public_student(s)


@router.patch("/students/{student_id}")
async def update_student(
    student_id: str,
    payload: StudentIn,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_feature("students")),
):
    tdb = tenant_db(user["tenant_id"])
    s = await get_student_or_404(user["tenant_id"], student_id)
    if not can_access(user, s):
        raise HTTPException(status_code=403, detail="Forbidden")
    upd = {
        **payload.model_dump(),
        "updated_at": now_utc(),
        "updated_by_user_id": user["_id"],
        "updated_by_name": user.get("name") or user.get("email"),
    }
    await tdb.students.update_one({"_id": student_id}, {"$set": upd})
    s2 = await tdb.students.find_one({"_id": student_id})
    await audit(user["tenant_id"], user["_id"], "student.update", student_id, {"name": payload.name})
    background_tasks.add_task(sync_to_sheets, user, s2, "update")
    return public_student(s2)


@router.delete("/students/{student_id}")
async def delete_student(
    student_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_feature("students")),
):
    tdb = tenant_db(user["tenant_id"])
    s = await get_student_or_404(user["tenant_id"], student_id)
    if not can_access(user, s):
        raise HTTPException(status_code=403, detail="Forbidden")
    await tdb.students.update_one(
        {"_id": student_id}, {"$set": {"deleted_at": now_utc()}}
    )
    await audit(user["tenant_id"], user["_id"], "student.delete", student_id, {})
    background_tasks.add_task(sync_to_sheets, user, s, "delete")
    return {"ok": True}

"""Student document model — see /app/backend/app/routes/students_crud.py for usage.

This is the SOURCE OF TRUTH for the `students` collection in every per-employer DB.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StudentFileMeta(BaseModel):
    """A single uploaded file inside a student's `files` map."""
    file_id: str
    filename: str = ""
    mime: str = ""
    size: int = 0
    uploaded_at: datetime


class StudentDoc(BaseModel):
    """Authoritative Mongo doc shape for `students` collection.

    Routes should construct one of these, then call `.model_dump(mode="json")`
    when inserting/updating. Reads should validate via `StudentDoc.model_validate`
    so the rest of the code never deals with raw dicts.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    # `_id` arrives as either "_id" (from Mongo) or "id" (from API responses).
    id: str = Field(..., alias="_id")
    employer_id: str
    owner_user_id: str
    owner_name: str = ""

    # Auto-incremented per employer; we keep both the int (for sorting) and
    # the string (for display).
    serial_no_int: int
    serial_no: str

    # 19 student fields — keep order matching frontend FILE_SLOTS for layout
    # parity. All are optional / string for forgiving entry.
    name: str
    fathers_name: Optional[str] = ""
    mothers_name: Optional[str] = ""
    dob: Optional[str] = ""
    aadhaar: Optional[str] = ""               # masked in API responses
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

    # Uploaded files keyed by slot code (e.g. "photo", "tenth_marksheet").
    files: dict[str, StudentFileMeta] = Field(default_factory=dict)

    # Google Sheets mirror state.
    google_sheet_row: Optional[int] = None

    # Lifecycle.
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    updated_by_user_id: Optional[str] = None
    updated_by_name: Optional[str] = None


# Index hints — read by services/migrate.py on boot.
STUDENT_INDEXES = (
    [("owner_user_id", 1)],
    [("deleted_at", 1)],
    [("serial_no_int", -1)],
)

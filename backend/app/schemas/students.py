"""Students module schemas — CRUD payload + Sheets configuration."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class StudentIn(BaseModel):
    """Inbound payload for create + patch. PATCH semantics use
    `model_dump(exclude_unset=True)` so missing fields are ignored."""
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


class SheetConfigurePayload(BaseModel):
    """Bind a Google spreadsheet to the employer's students module.
    Accepts either a raw spreadsheet ID or a full Sheets URL."""
    url_or_id: str = Field(..., min_length=10)

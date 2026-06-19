"""Attendance record document — `attendance` collection in each employer's DB."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AttendanceDoc(BaseModel):
    """One check-in OR check-out event. A complete day = at least one of each."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str = Field(..., alias="_id")
    employer_id: str
    employee_id: str
    date: str                 # ISO yyyy-mm-dd (local IST)
    type: str                 # "check_in" | "check_out"
    method: str = "normal"    # "normal" | "facial" | "facial_voice"

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    in_geofence: Optional[bool] = None

    facial_match: Optional[bool] = None
    facial_score: Optional[float] = None

    notes: Optional[str] = None
    timestamp: datetime       # UTC, tz-aware
    backdated: bool = False
    created_by: Optional[str] = None  # user_id (when employer marks on behalf)


ATTENDANCE_INDEXES = (
    [("employee_id", 1), ("date", 1)],
    [("date", 1)],
)

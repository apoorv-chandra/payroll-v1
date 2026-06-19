"""Attendance schemas: mark in/out, backdated delete."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class MarkAttendanceRequest(BaseModel):
    method: Literal["normal", "facial", "facial_voice"] = "normal"
    type: Literal["check_in", "check_out"] = "check_in"
    date: Optional[str] = None  # ISO yyyy-mm-dd; if omitted server uses today
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    facial_image: Optional[str] = None
    notes: Optional[str] = None
    overwrite: bool = False  # only honored if no payroll for that month


class AttendanceDeleteRequest(BaseModel):
    date: str  # ISO

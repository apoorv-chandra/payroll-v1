"""Leave application + decision schemas."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class ApplyLeaveRequest(BaseModel):
    leave_type: str
    from_date: str
    to_date: str
    reason: Optional[str] = None
    half_day: bool = False


class LeaveDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: Optional[str] = None
    decided_at_local: Optional[str] = None  # client's local timestamp string

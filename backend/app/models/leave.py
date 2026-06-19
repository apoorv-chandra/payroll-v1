"""Leave application + balance documents (per-employer DB)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LeaveApplicationDoc(BaseModel):
    """`leave_applications` — one employee's leave request, with audit trail."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str = Field(..., alias="_id")
    employer_id: str
    employee_id: str
    leave_type: str           # matches a settings.leave_types[].code
    from_date: str            # ISO yyyy-mm-dd
    to_date: str
    days: float               # 0.5 for half-day
    half_day: bool = False
    reason: Optional[str] = None

    status: str = "pending"   # "pending" | "approved" | "rejected"
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    decided_at_local: Optional[str] = None  # client local timestamp string
    decision_note: Optional[str] = None

    applied_at: datetime


class LeaveBalanceDoc(BaseModel):
    """`leave_balances` — one row per (employee, leave_type) for the current
    fiscal year. Pending applications consume `pending`; approved ones move
    into `used`."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str = Field(..., alias="_id")
    employer_id: str
    employee_id: str
    leave_type: str
    quota: float
    used: float = 0.0
    pending: float = 0.0
    fiscal_start: str         # ISO yyyy-mm-dd


LEAVE_APPLICATION_INDEXES = (
    [("employee_id", 1)],
    [("status", 1)],
)
LEAVE_BALANCE_INDEXES = (
    [("employee_id", 1), ("leave_type", 1)],
)

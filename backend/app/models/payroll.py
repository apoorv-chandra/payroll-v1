"""Payroll run + line item documents (per-employer DB).

State machine for `PayrollRunDoc.status`:

    draft → pending_approval → approved → disbursed
              ↘ rejected                  ↘ deleted (frees the month again)
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PayrollItemDoc(BaseModel):
    """One employee's line in a payroll run."""
    employee_id: str
    emp_code: str
    name: str

    monthly_salary: float
    days_present: float
    days_payable: float       # may include half-day leaves etc.

    gross: float
    deductions: float = 0.0
    deduction_note: Optional[str] = None
    net: float

    disbursed: bool = False
    disbursed_at: Optional[datetime] = None
    disbursed_method: Optional[str] = None  # "cash" | "online"
    disbursed_txn_id: Optional[str] = None
    disbursed_by: Optional[str] = None


class PayrollRunDoc(BaseModel):
    """`payroll_runs` — one document per (employer, month, year)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str = Field(..., alias="_id")
    employer_id: str
    month: int                # 1-12
    year: int

    status: str = "draft"     # see state machine in module docstring
    working_days: int = 26

    items: List[PayrollItemDoc] = Field(default_factory=list)
    total_gross: float = 0.0
    total_deductions: float = 0.0
    total_net: float = 0.0

    # Lifecycle audit.
    generated_by: Optional[str] = None
    generated_at: datetime
    submitted_by: Optional[str] = None
    submitted_at: Optional[datetime] = None
    submit_note: Optional[str] = None
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    decided_at_local: Optional[str] = None
    decision_note: Optional[str] = None


PAYROLL_RUN_INDEXES = (
    [("year", -1), ("month", -1)],
    [("status", 1)],
)

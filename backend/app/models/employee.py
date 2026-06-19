"""Employee profile document — `employees` collection in each employer's DB."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EmployeeDoc(BaseModel):
    """Authoritative shape for `<employer_db>.employees`."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str = Field(..., alias="_id")
    employer_id: str
    user_id: str             # ← UserDoc.id (global)

    emp_code: str
    name: str
    email: EmailStr
    phone: Optional[str] = None

    designation: Optional[str] = None
    department: Optional[str] = None
    monthly_salary: float = 0.0
    joining_date: Optional[str] = None  # ISO yyyy-mm-dd
    bank_account: Optional[str] = None
    ifsc: Optional[str] = None

    elevated_roles: List[str] = Field(default_factory=list)
    attendance_config_id: int = 1
    active: bool = True

    # Self-signup workflow.
    self_signup: bool = False
    signup_status: Optional[str] = None  # "pending" | "approved" | "rejected"
    consent_given_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None

    created_at: datetime


EMPLOYEE_INDEXES = (
    [("emp_code", 1)],
    [("user_id", 1)],
    [("signup_status", 1)],
)

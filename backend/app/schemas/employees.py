"""Employee CRUD + approval schemas."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class CreateEmployeeRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    emp_code: str
    designation: Optional[str] = None
    department: Optional[str] = None
    monthly_salary: float = Field(ge=0)
    joining_date: Optional[str] = None
    bank_account: Optional[str] = None
    ifsc: Optional[str] = None
    elevated_roles: List[str] = []  # accountant / principal / cashier
    attendance_config_id: int = 1
    phone: Optional[str] = None  # WhatsApp number


class UpdateEmployeeRequest(BaseModel):
    name: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    monthly_salary: Optional[float] = None
    bank_account: Optional[str] = None
    ifsc: Optional[str] = None
    elevated_roles: Optional[List[str]] = None
    attendance_config_id: Optional[int] = None
    active: Optional[bool] = None
    phone: Optional[str] = None


class ApproveSignupRequest(BaseModel):
    """Employer fills in fields when approving a pending self-signup.
    All optional — employer fills only what they need."""
    emp_code: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    monthly_salary: Optional[float] = Field(default=None, ge=0)
    joining_date: Optional[str] = None
    bank_account: Optional[str] = None
    ifsc: Optional[str] = None
    elevated_roles: Optional[List[str]] = None
    attendance_config_id: Optional[int] = None

"""All request/response Pydantic models."""
from __future__ import annotations

from typing import Optional, List, Literal
from pydantic import BaseModel, Field, EmailStr


# ---------- Auth ----------
class CaptchaIssue(BaseModel):
    token: str
    a: int
    b: int
    op: str  # "+" or "-"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    captcha_token: Optional[str] = None
    captcha_answer: Optional[int] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class SignupRequest(BaseModel):
    """Public, employee self-serve onboarding (SaaS distribution)."""
    signup_code: str = Field(min_length=6, max_length=16)
    name: str
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    phone: Optional[str] = None
    consent: bool = False
    captcha_token: Optional[str] = None
    captcha_answer: Optional[int] = None


class EmployerPublic(BaseModel):
    id: str
    name: str


# ---------- Tenants ----------
class CreateEmployerRequest(BaseModel):
    name: str
    admin_email: EmailStr
    admin_password: str
    admin_name: str
    address: Optional[str] = None
    phone: Optional[str] = None


# ---------- Employees ----------
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
    """All fields optional — employer fills only what they need to set."""
    emp_code: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    monthly_salary: Optional[float] = Field(default=None, ge=0)
    joining_date: Optional[str] = None
    bank_account: Optional[str] = None
    ifsc: Optional[str] = None
    elevated_roles: Optional[List[str]] = None
    attendance_config_id: Optional[int] = None


# ---------- Tenant settings ----------
class GeoFenceConfig(BaseModel):
    enabled: bool = False
    center_lat: Optional[float] = None
    center_lng: Optional[float] = None
    radius_m: Optional[int] = None


class AttendanceConfigRequest(BaseModel):
    default_config_id: int = 1
    geo_fence: GeoFenceConfig = GeoFenceConfig()
    working_days_per_month: int = 26


class LeaveTypeReq(BaseModel):
    code: str
    name: str
    annual_quota: float
    carry_forward: bool = False
    paid: bool = True


class TenantSettingsUpdate(BaseModel):
    leave_types: Optional[List[LeaveTypeReq]] = None
    leave_reset_month: Optional[int] = None
    attendance: Optional[AttendanceConfigRequest] = None
    company_logo_url: Optional[str] = None


# ---------- Attendance ----------
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


# ---------- Leave ----------
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


# ---------- Payroll ----------
class GeneratePayrollRequest(BaseModel):
    month: int
    year: int


class PayrollItemDeductionUpdate(BaseModel):
    deductions: float = Field(ge=0)
    note: Optional[str] = None


class PayrollSubmitRequest(BaseModel):
    note: Optional[str] = None


class PayrollDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: Optional[str] = None
    decided_at_local: Optional[str] = None


class DisburseRequest(BaseModel):
    method: Literal["cash", "online"] = "cash"


# ---------- Platform settings (super admin) ----------
class PlatformSettingsUpdate(BaseModel):
    whatsapp_enabled: Optional[bool] = None
    max_backdate_days: Optional[int] = Field(default=None, ge=0, le=365)

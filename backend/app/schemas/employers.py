"""Employer (tenant) related schemas — both public-facing and super-admin only."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class EmployerPublic(BaseModel):
    """Light public-facing employer card (used in legacy `/auth/employers`)."""
    id: str
    name: str


class CreateEmployerRequest(BaseModel):
    """Super-admin onboards a new employer + their admin user in one shot."""
    name: str
    admin_email: EmailStr
    admin_password: str
    admin_name: str
    address: Optional[str] = None
    phone: Optional[str] = None


# ---------- Employer settings (formerly TenantSettingsUpdate) ----------
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
    """Employer-admin updates settings for their own tenant. Name kept for
    backward-compat with the existing route handler signature."""
    leave_types: Optional[List[LeaveTypeReq]] = None
    leave_reset_month: Optional[int] = None
    attendance: Optional[AttendanceConfigRequest] = None
    company_logo_url: Optional[str] = None


# ---------- Platform settings (super-admin only) ----------
class PlatformSettingsUpdate(BaseModel):
    whatsapp_enabled: Optional[bool] = None
    max_backdate_days: Optional[int] = Field(default=None, ge=0, le=365)

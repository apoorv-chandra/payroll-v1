"""User document — global `users` collection.

Auth identity. Per-employer profile data lives in `EmployeeDoc` (which sits in
the per-employer database). The two are joined via `employee_id` ↔ `user_id`.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserDoc(BaseModel):
    """Authoritative shape for `db.users` (global)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str = Field(..., alias="_id")
    email: EmailStr
    name: str
    role: str  # "super_admin" | "employer" | "employee"
    employer_id: Optional[str] = None
    employee_id: Optional[str] = None  # link to EmployeeDoc in employer DB

    password_hash: str
    # Plaintext ONLY between issuance and first login. Auto-cleared on
    # successful login. NEVER serialise this field out of the API.
    initial_password_plain: Optional[str] = None

    elevated_roles: List[str] = Field(default_factory=list)  # accountant/principal/cashier
    phone: Optional[str] = None

    # Module-based RBAC override per user (subset of employer's enabled_features).
    feature_permissions: List[str] = Field(default_factory=list)

    disabled: bool = False           # blocks login (used for pending signups)
    first_login_at: Optional[datetime] = None
    password_changed_at: Optional[datetime] = None
    password_reset_at: Optional[datetime] = None

    created_at: datetime


USER_INDEXES = (
    [("email", 1)],
    [("employer_id", 1)],
)

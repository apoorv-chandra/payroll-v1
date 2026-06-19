"""Employer (tenant) document — global `employers` collection."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class EmployerDoc(BaseModel):
    """Authoritative shape for `db.employers` (global)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str = Field(..., alias="_id")
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    active: bool = True

    # Immutable 8-char invite code (`A-Z2-9` without 0/O/1/I/L). Public signups
    # need this to register against the right employer.
    signup_code: Optional[str] = None

    # Module-based RBAC. Lists of feature codes the super-admin has unlocked.
    enabled_features: List[str] = Field(default_factory=lambda: ["payroll"])

    # Google Sheets binding (students module).
    students_sheet_id: Optional[str] = None
    students_sheet_url: Optional[str] = None

    settings: dict = Field(default_factory=dict)
    created_at: datetime


# Indexes consumed by services/migrate.py on boot.
EMPLOYER_INDEXES = (
    [("signup_code", 1)],
)

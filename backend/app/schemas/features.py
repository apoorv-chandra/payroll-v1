"""Feature-permission schemas (RBAC module gating)."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class FeatureCodesPayload(BaseModel):
    """Set the list of enabled feature codes for an employer or employee.
    Empty list = revoke all modules."""
    codes: List[str] = Field(default_factory=list)

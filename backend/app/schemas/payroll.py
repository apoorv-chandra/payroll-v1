"""Payroll run lifecycle schemas."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


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

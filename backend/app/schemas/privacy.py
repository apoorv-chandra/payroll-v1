"""DPDP consent schemas."""
from __future__ import annotations

from pydantic import BaseModel


class ConsentSet(BaseModel):
    """Wrapped { key: bool } map of consent flags. Only keys present in the
    payload get updated; unknown keys are silently dropped by the route."""
    consents: dict

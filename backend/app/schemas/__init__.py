"""Request/response schemas — split per domain for maintainability.

This `__init__.py` re-exports every public schema so existing route imports
(`from ..schemas import LoginRequest, ...`) keep working unchanged.

NEW IMPORTS should prefer the explicit domain module, e.g.

    from ..schemas.auth import LoginRequest, TokenResponse
    from ..schemas.payroll import GeneratePayrollRequest

…to keep call sites self-documenting.
"""
from __future__ import annotations

from .auth import (
    CaptchaIssue,
    LoginRequest,
    SignupRequest,
    TokenResponse,
)
from .employers import (
    AttendanceConfigRequest,
    CreateEmployerRequest,
    EmployerPublic,
    GeoFenceConfig,
    LeaveTypeReq,
    PlatformSettingsUpdate,
    TenantSettingsUpdate,
)
from .employees import (
    ApproveSignupRequest,
    CreateEmployeeRequest,
    UpdateEmployeeRequest,
)
from .attendance import (
    AttendanceDeleteRequest,
    MarkAttendanceRequest,
)
from .leaves import (
    ApplyLeaveRequest,
    LeaveDecision,
)
from .payroll import (
    DisburseRequest,
    GeneratePayrollRequest,
    PayrollDecision,
    PayrollItemDeductionUpdate,
    PayrollSubmitRequest,
)
from .features import FeatureCodesPayload
from .privacy import ConsentSet
from .students import SheetConfigurePayload, StudentIn

__all__ = [
    # auth
    "CaptchaIssue", "LoginRequest", "SignupRequest", "TokenResponse",
    # employers / platform
    "AttendanceConfigRequest", "CreateEmployerRequest", "EmployerPublic",
    "GeoFenceConfig", "LeaveTypeReq", "PlatformSettingsUpdate",
    "TenantSettingsUpdate",
    # employees
    "ApproveSignupRequest", "CreateEmployeeRequest", "UpdateEmployeeRequest",
    # attendance
    "AttendanceDeleteRequest", "MarkAttendanceRequest",
    # leaves
    "ApplyLeaveRequest", "LeaveDecision",
    # payroll
    "DisburseRequest", "GeneratePayrollRequest", "PayrollDecision",
    "PayrollItemDeductionUpdate", "PayrollSubmitRequest",
    # features / privacy / students
    "FeatureCodesPayload", "ConsentSet", "SheetConfigurePayload", "StudentIn",
]

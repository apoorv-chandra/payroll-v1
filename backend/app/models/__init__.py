"""Domain document models — the canonical shape of every entity stored in Mongo.

Each module under this package defines a single Pydantic model representing a
collection's document. These are the **source of truth** for schema. Routes
should accept inbound payloads via `app/schemas/*` request models and write
outbound responses via the `model_dump()` of these docs.

Convention
----------
  • All IDs are UUID-strings (`gen_id()`). No ObjectIds.
  • All datetimes are tz-aware UTC (`datetime.now(timezone.utc)`).
  • Per-employer scoping is via `employer_id` (legacy field name `tenant_id`
    has been migrated away — see services/rename_to_employers.py).
  • Soft-delete via nullable `deleted_at` where applicable.
"""
from .attendance import AttendanceDoc, ATTENDANCE_INDEXES
from .employee import EmployeeDoc, EMPLOYEE_INDEXES
from .employer import EmployerDoc, EMPLOYER_INDEXES
from .leave import (
    LeaveApplicationDoc,
    LeaveBalanceDoc,
    LEAVE_APPLICATION_INDEXES,
    LEAVE_BALANCE_INDEXES,
)
from .payroll import PayrollItemDoc, PayrollRunDoc, PAYROLL_RUN_INDEXES
from .student import StudentDoc, StudentFileMeta, STUDENT_INDEXES
from .user import UserDoc, USER_INDEXES

__all__ = [
    "AttendanceDoc", "ATTENDANCE_INDEXES",
    "EmployeeDoc", "EMPLOYEE_INDEXES",
    "EmployerDoc", "EMPLOYER_INDEXES",
    "LeaveApplicationDoc", "LeaveBalanceDoc",
    "LEAVE_APPLICATION_INDEXES", "LEAVE_BALANCE_INDEXES",
    "PayrollItemDoc", "PayrollRunDoc", "PAYROLL_RUN_INDEXES",
    "StudentDoc", "StudentFileMeta", "STUDENT_INDEXES",
    "UserDoc", "USER_INDEXES",
]

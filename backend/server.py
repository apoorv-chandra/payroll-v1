from dotenv import load_dotenv
load_dotenv()

import os
import io
import uuid
import math
import base64
import asyncio
import logging
import bcrypt
import jwt
import resend
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List, Literal
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request, Response, status, APIRouter, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, EmailStr
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("payroll")
logging.basicConfig(level=logging.INFO)

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

# ---------- Config ----------
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@payroll.app").lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "Payroll <onboarding@resend.dev>")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "")
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

# ---------- DB ----------
client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# ---------- Helpers ----------
def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode("utf-8"), h.encode("utf-8"))
    except Exception:
        return False

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def create_access_token(user_id: str, role: str, tenant_id: Optional[str]) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "tenant_id": tenant_id,
        "exp": now_utc() + timedelta(hours=12),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def gen_id() -> str:
    return str(uuid.uuid4())

def public_user(u: dict) -> dict:
    return {
        "id": u["_id"],
        "email": u["email"],
        "name": u.get("name"),
        "role": u["role"],
        "tenant_id": u.get("tenant_id"),
        "employee_id": u.get("employee_id"),
        "elevated_roles": u.get("elevated_roles", []),
        "created_at": u.get("created_at"),
    }

# ---------- Auth dependency ----------
async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": payload["sub"]}, {"password_hash": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["id"] = user["_id"]
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def require_role(*roles: str):
    async def dep(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Forbidden: insufficient role")
        return user
    return dep

def require_employer_or_admin(user: dict = Depends(get_current_user)):
    if user["role"] not in ("super_admin", "employer"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return user

# ---------- Lifespan / startup ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Indexes
    await db.users.create_index("email", unique=True)
    await db.tenants.create_index("name")
    await db.employees.create_index([("tenant_id", 1), ("emp_code", 1)], unique=True)
    await db.employees.create_index([("tenant_id", 1), ("user_id", 1)])
    await db.attendance.create_index([("tenant_id", 1), ("employee_id", 1), ("date", 1)], unique=True)
    await db.leave_applications.create_index([("tenant_id", 1), ("employee_id", 1)])
    await db.leave_balances.create_index([("tenant_id", 1), ("employee_id", 1), ("leave_type", 1)], unique=True)
    await db.payroll_runs.create_index([("tenant_id", 1), ("month", 1), ("year", 1)])
    await db.payroll_items.create_index([("payroll_run_id", 1), ("employee_id", 1)], unique=True)
    await db.audit_logs.create_index([("tenant_id", 1), ("created_at", -1)])

    # Seed super admin
    existing = await db.users.find_one({"email": ADMIN_EMAIL})
    if existing is None:
        await db.users.insert_one({
            "_id": gen_id(),
            "email": ADMIN_EMAIL,
            "password_hash": hash_password(ADMIN_PASSWORD),
            "name": "Super Admin",
            "role": "super_admin",
            "tenant_id": None,
            "created_at": now_utc(),
        })
    elif not verify_password(ADMIN_PASSWORD, existing["password_hash"]):
        await db.users.update_one(
            {"email": ADMIN_EMAIL},
            {"$set": {"password_hash": hash_password(ADMIN_PASSWORD)}},
        )
    yield

app = FastAPI(title="Payroll & Attendance API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")

# ============================================================
#                 SCHEMAS
# ============================================================
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class CreateEmployerRequest(BaseModel):
    name: str
    admin_email: EmailStr
    admin_password: str
    admin_name: str
    address: Optional[str] = None
    phone: Optional[str] = None

class CreateEmployeeRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    emp_code: str
    designation: Optional[str] = None
    department: Optional[str] = None
    monthly_salary: float = Field(ge=0)
    joining_date: Optional[str] = None  # ISO date
    bank_account: Optional[str] = None
    ifsc: Optional[str] = None
    elevated_roles: List[str] = []  # accountant, principal, cashier
    attendance_config_id: int = 1
    phone: Optional[str] = None

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

class GeoFenceConfig(BaseModel):
    enabled: bool = False
    center_lat: Optional[float] = None
    center_lng: Optional[float] = None
    radius_m: Optional[int] = None  # meters

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
    leave_reset_month: Optional[int] = None  # 1-12
    attendance: Optional[AttendanceConfigRequest] = None
    company_logo_url: Optional[str] = None

class MarkAttendanceRequest(BaseModel):
    method: Literal["normal", "facial", "facial_voice"] = "normal"
    type: Literal["check_in", "check_out"] = "check_in"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    facial_image: Optional[str] = None  # base64 (stored hash only)
    notes: Optional[str] = None

class ApplyLeaveRequest(BaseModel):
    leave_type: str
    from_date: str  # ISO
    to_date: str    # ISO
    reason: Optional[str] = None
    half_day: bool = False

class LeaveDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: Optional[str] = None

class GeneratePayrollRequest(BaseModel):
    month: int  # 1-12
    year: int

class PayrollDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: Optional[str] = None

class DisburseRequest(BaseModel):
    method: Literal["cash", "online"] = "cash"

# ============================================================
#                 AUDIT
# ============================================================
async def audit(tenant_id: Optional[str], actor_id: str, action: str, target: Optional[str] = None, meta: Optional[dict] = None):
    await db.audit_logs.insert_one({
        "_id": gen_id(),
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "action": action,
        "target": target,
        "meta": meta or {},
        "created_at": now_utc(),
    })

# ============================================================
#                 EMAIL (Resend)
# ============================================================
EMAIL_LAYOUT = """
<!doctype html><html><body style="margin:0;background:#F9FAFB;font-family:'Helvetica Neue',Arial,sans-serif;color:#0A0A0A;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F9FAFB;padding:24px 0;">
  <tr><td align="center">
    <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;">
      <tr><td style="padding:20px 24px;border-bottom:1px solid #F3F4F6;">
        <table role="presentation" width="100%"><tr>
          <td style="font-weight:700;font-size:18px;letter-spacing:-0.01em;">Payroll</td>
          <td align="right" style="font-size:11px;color:#737373;text-transform:uppercase;letter-spacing:0.12em;">{tag}</td>
        </tr></table>
      </td></tr>
      <tr><td style="padding:24px;">{body}</td></tr>
      <tr><td style="padding:16px 24px;border-top:1px solid #F3F4F6;font-size:11px;color:#9CA3AF;">
        Sent by Payroll & Attendance. If this wasn't you, ignore this email.
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>
"""

def render_email(tag: str, body_html: str) -> str:
    return EMAIL_LAYOUT.format(tag=tag, body=body_html)

async def send_email(to: str, subject: str, html: str, attachments: Optional[List[dict]] = None) -> Optional[str]:
    """Non-blocking email send. Logs and swallows failures so app flows aren't blocked."""
    if not RESEND_API_KEY:
        logger.info(f"[email-mock] to={to} subject={subject}")
        return None
    params = {"from": SENDER_EMAIL, "to": [to], "subject": subject, "html": html}
    if attachments:
        params["attachments"] = attachments
    try:
        res = await asyncio.to_thread(resend.Emails.send, params)
        eid = (res or {}).get("id") if isinstance(res, dict) else getattr(res, "id", None)
        logger.info(f"[email-sent] to={to} id={eid}")
        return eid
    except Exception as e:
        logger.error(f"[email-fail] to={to} subject={subject} err={e}")
        return None

def login_url() -> str:
    return f"{APP_BASE_URL}/login" if APP_BASE_URL else "/login"

# ============================================================
#                 AUTH
# ============================================================
@api.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, response: Response):
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.get("disabled"):
        raise HTTPException(status_code=403, detail="Account disabled")
    token = create_access_token(user["_id"], user["role"], user.get("tenant_id"))
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax", max_age=43200, path="/")
    return TokenResponse(access_token=token, user=public_user(user))

@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}

@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)

# ============================================================
#                 SUPER ADMIN: TENANTS / EMPLOYERS
# ============================================================
@api.post("/admin/employers")
async def create_employer(req: CreateEmployerRequest, user: dict = Depends(require_role("super_admin"))):
    admin_email = req.admin_email.lower().strip()
    if await db.users.find_one({"email": admin_email}):
        raise HTTPException(status_code=400, detail="Email already in use")
    tenant_id = gen_id()
    await db.tenants.insert_one({
        "_id": tenant_id,
        "name": req.name,
        "address": req.address,
        "phone": req.phone,
        "created_at": now_utc(),
        "active": True,
        "settings": {
            "leave_reset_month": 4,  # April default (Indian fiscal)
            "leave_types": default_leave_types(),
            "attendance": {
                "default_config_id": 1,
                "geo_fence": {"enabled": False},
                "working_days_per_month": 26,
            },
            "company_logo_url": None,
        },
    })
    employer_user_id = gen_id()
    await db.users.insert_one({
        "_id": employer_user_id,
        "email": admin_email,
        "password_hash": hash_password(req.admin_password),
        "name": req.admin_name,
        "role": "employer",
        "tenant_id": tenant_id,
        "created_at": now_utc(),
    })
    await audit(tenant_id, user["_id"], "tenant.create", tenant_id, {"name": req.name})
    return {"id": tenant_id, "admin_user_id": employer_user_id}

@api.get("/admin/employers")
async def list_employers(user: dict = Depends(require_role("super_admin"))):
    out = []
    async for t in db.tenants.find({}, {}).sort("created_at", -1):
        admin = await db.users.find_one({"tenant_id": t["_id"], "role": "employer"}, {"password_hash": 0})
        emp_count = await db.employees.count_documents({"tenant_id": t["_id"]})
        t["id"] = t["_id"]
        t["admin"] = public_user(admin) if admin else None
        t["employee_count"] = emp_count
        out.append({k: v for k, v in t.items() if k != "_id"})
    return out

@api.delete("/admin/employers/{tenant_id}")
async def delete_employer(tenant_id: str, user: dict = Depends(require_role("super_admin"))):
    await db.tenants.delete_one({"_id": tenant_id})
    await db.users.delete_many({"tenant_id": tenant_id})
    await db.employees.delete_many({"tenant_id": tenant_id})
    await db.attendance.delete_many({"tenant_id": tenant_id})
    await db.leave_applications.delete_many({"tenant_id": tenant_id})
    await db.leave_balances.delete_many({"tenant_id": tenant_id})
    await db.payroll_runs.delete_many({"tenant_id": tenant_id})
    await db.payroll_items.delete_many({"tenant_id": tenant_id})
    await audit(None, user["_id"], "tenant.delete", tenant_id)
    return {"ok": True}

@api.get("/admin/audit")
async def list_audit(user: dict = Depends(require_role("super_admin")), limit: int = 100):
    items = []
    async for a in db.audit_logs.find().sort("created_at", -1).limit(limit):
        a["id"] = a["_id"]
        items.append({k: v for k, v in a.items() if k != "_id"})
    return items

@api.get("/admin/stats")
async def admin_stats(user: dict = Depends(require_role("super_admin"))):
    return {
        "tenants": await db.tenants.count_documents({}),
        "employees": await db.employees.count_documents({}),
        "attendance_today": await db.attendance.count_documents({"date": today_iso()}),
        "active_payrolls": await db.payroll_runs.count_documents({"status": {"$in": ["draft", "approved"]}}),
    }

def default_leave_types() -> list:
    return [
        {"code": "CL", "name": "Casual Leave", "annual_quota": 12, "carry_forward": False, "paid": True},
        {"code": "SL", "name": "Sick Leave", "annual_quota": 8, "carry_forward": True, "paid": True},
        {"code": "OD", "name": "On-Duty", "annual_quota": 0, "carry_forward": False, "paid": True},
        {"code": "HD", "name": "Half-Day", "annual_quota": 0, "carry_forward": False, "paid": True},
        {"code": "CO", "name": "Comp-Off", "annual_quota": 0, "carry_forward": True, "paid": True},
    ]

def today_iso() -> str:
    return date.today().isoformat()

# ============================================================
#                 EMPLOYER: SETTINGS
# ============================================================
async def get_tenant(tenant_id: str) -> dict:
    t = await db.tenants.find_one({"_id": tenant_id})
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return t

@api.get("/tenant/settings")
async def get_settings(user: dict = Depends(require_employer_or_admin)):
    if user["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Super admin has no tenant; pass tenant_id")
    t = await get_tenant(user["tenant_id"])
    return {"id": t["_id"], "name": t["name"], "settings": t.get("settings", {}), "address": t.get("address"), "phone": t.get("phone")}

@api.put("/tenant/settings")
async def update_settings(req: TenantSettingsUpdate, user: dict = Depends(require_role("employer"))):
    upd = {}
    if req.leave_types is not None:
        upd["settings.leave_types"] = [lt.model_dump() for lt in req.leave_types]
    if req.leave_reset_month is not None:
        upd["settings.leave_reset_month"] = req.leave_reset_month
    if req.attendance is not None:
        upd["settings.attendance"] = req.attendance.model_dump()
    if req.company_logo_url is not None:
        upd["settings.company_logo_url"] = req.company_logo_url
    if upd:
        await db.tenants.update_one({"_id": user["tenant_id"]}, {"$set": upd})
    await audit(user["tenant_id"], user["_id"], "tenant.settings.update", user["tenant_id"], upd)
    t = await get_tenant(user["tenant_id"])
    return t.get("settings", {})

# ============================================================
#                 EMPLOYER: EMPLOYEES
# ============================================================
async def reset_leave_balances(tenant_id: str, employee_id: str, joining_date: Optional[str] = None):
    t = await get_tenant(tenant_id)
    leave_types = t.get("settings", {}).get("leave_types", default_leave_types())
    # Pro-rate if joined this fiscal year
    today = date.today()
    reset_month = t.get("settings", {}).get("leave_reset_month", 4)
    fiscal_start = date(today.year if today.month >= reset_month else today.year - 1, reset_month, 1)
    join = None
    if joining_date:
        try:
            join = date.fromisoformat(joining_date)
        except Exception:
            join = None
    months_remaining = 12
    if join and join > fiscal_start:
        months_remaining = max(1, 12 - ((join.year - fiscal_start.year) * 12 + (join.month - fiscal_start.month)))
    for lt in leave_types:
        prorated = round((lt["annual_quota"] * months_remaining) / 12.0, 2)
        await db.leave_balances.update_one(
            {"tenant_id": tenant_id, "employee_id": employee_id, "leave_type": lt["code"]},
            {
                "$set": {
                    "tenant_id": tenant_id,
                    "employee_id": employee_id,
                    "leave_type": lt["code"],
                    "quota": prorated,
                    "used": 0,
                    "fiscal_start": fiscal_start.isoformat(),
                },
                "$setOnInsert": {"_id": gen_id(), "pending": 0},
            },
            upsert=True,
        )

@api.post("/employees")
async def create_employee(req: CreateEmployeeRequest, user: dict = Depends(require_role("employer"))):
    email = req.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already in use")
    if await db.employees.find_one({"tenant_id": user["tenant_id"], "emp_code": req.emp_code}):
        raise HTTPException(status_code=400, detail="Employee code already exists")
    emp_id = gen_id()
    user_id = gen_id()
    await db.users.insert_one({
        "_id": user_id,
        "email": email,
        "password_hash": hash_password(req.password),
        "name": req.name,
        "role": "employee",
        "tenant_id": user["tenant_id"],
        "employee_id": emp_id,
        "elevated_roles": req.elevated_roles or [],
        "created_at": now_utc(),
    })
    await db.employees.insert_one({
        "_id": emp_id,
        "tenant_id": user["tenant_id"],
        "user_id": user_id,
        "emp_code": req.emp_code,
        "name": req.name,
        "email": email,
        "phone": req.phone,
        "designation": req.designation,
        "department": req.department,
        "monthly_salary": req.monthly_salary,
        "joining_date": req.joining_date or today_iso(),
        "bank_account": req.bank_account,
        "ifsc": req.ifsc,
        "elevated_roles": req.elevated_roles or [],
        "attendance_config_id": req.attendance_config_id,
        "active": True,
        "created_at": now_utc(),
    })
    await reset_leave_balances(user["tenant_id"], emp_id, req.joining_date)
    await audit(user["tenant_id"], user["_id"], "employee.create", emp_id, {"name": req.name})
    # Welcome email with credentials
    tenant_doc = await db.tenants.find_one({"_id": user["tenant_id"]})
    company = (tenant_doc or {}).get("name", "Payroll")
    body = f"""
      <h2 style="margin:0 0 12px 0;font-size:20px;letter-spacing:-0.01em;">Welcome to {company} 👋</h2>
      <p style="margin:0 0 16px 0;color:#4B5563;line-height:1.55;">
        Your account has been created. You can now mark attendance, apply for leave and download salary slips from your phone.
      </p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px;width:100%;font-size:14px;">
        <tr><td style="padding:10px 14px;color:#737373;">Login email</td><td style="padding:10px 14px;font-weight:600;">{email}</td></tr>
        <tr><td style="padding:10px 14px;color:#737373;border-top:1px solid #F3F4F6;">Password</td><td style="padding:10px 14px;font-family:monospace;border-top:1px solid #F3F4F6;">{req.password}</td></tr>
        <tr><td style="padding:10px 14px;color:#737373;border-top:1px solid #F3F4F6;">Code</td><td style="padding:10px 14px;border-top:1px solid #F3F4F6;">{req.emp_code}</td></tr>
      </table>
      <p style="margin:18px 0 8px 0;">
        <a href="{login_url()}" style="display:inline-block;background:#0A0A0A;color:#FFFFFF;text-decoration:none;padding:12px 18px;border-radius:8px;font-weight:600;">Sign in to Payroll</a>
      </p>
      <p style="margin:8px 0 0 0;font-size:12px;color:#9CA3AF;">Please change your password after first login.</p>
    """
    asyncio.create_task(send_email(email, f"Welcome to {company} — your Payroll login", render_email("WELCOME", body)))
    return {"id": emp_id, "user_id": user_id}

@api.get("/employees")
async def list_employees(user: dict = Depends(require_employer_or_admin)):
    if user["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Use tenant scope")
    out = []
    async for e in db.employees.find({"tenant_id": user["tenant_id"]}).sort("emp_code", 1):
        e["id"] = e["_id"]
        out.append({k: v for k, v in e.items() if k != "_id"})
    return out

@api.get("/employees/{employee_id}")
async def get_employee(employee_id: str, user: dict = Depends(get_current_user)):
    e = await db.employees.find_one({"_id": employee_id})
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] != "super_admin" and e["tenant_id"] != user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Forbidden")
    e["id"] = e["_id"]
    return {k: v for k, v in e.items() if k != "_id"}

@api.put("/employees/{employee_id}")
async def update_employee(employee_id: str, req: UpdateEmployeeRequest, user: dict = Depends(require_role("employer"))):
    e = await db.employees.find_one({"_id": employee_id, "tenant_id": user["tenant_id"]})
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    upd = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
    if upd:
        await db.employees.update_one({"_id": employee_id}, {"$set": upd})
        if "name" in upd or "elevated_roles" in upd:
            user_upd = {}
            if "name" in upd:
                user_upd["name"] = upd["name"]
            if "elevated_roles" in upd:
                user_upd["elevated_roles"] = upd["elevated_roles"]
            await db.users.update_one({"_id": e["user_id"]}, {"$set": user_upd})
    await audit(user["tenant_id"], user["_id"], "employee.update", employee_id, upd)
    return {"ok": True}

@api.delete("/employees/{employee_id}")
async def delete_employee(employee_id: str, user: dict = Depends(require_role("employer"))):
    e = await db.employees.find_one({"_id": employee_id, "tenant_id": user["tenant_id"]})
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    await db.employees.delete_one({"_id": employee_id})
    await db.users.delete_one({"_id": e["user_id"]})
    await db.attendance.delete_many({"employee_id": employee_id})
    await db.leave_applications.delete_many({"employee_id": employee_id})
    await db.leave_balances.delete_many({"employee_id": employee_id})
    await audit(user["tenant_id"], user["_id"], "employee.delete", employee_id)
    return {"ok": True}

# ============================================================
#                 ATTENDANCE
# ============================================================
def haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@api.post("/attendance/mark")
async def mark_attendance(req: MarkAttendanceRequest, user: dict = Depends(require_role("employee"))):
    emp_id = user.get("employee_id")
    if not emp_id:
        raise HTTPException(status_code=400, detail="No employee profile linked")
    employee = await db.employees.find_one({"_id": emp_id})
    if not employee or not employee.get("active", True):
        raise HTTPException(status_code=403, detail="Employee inactive")
    tenant = await get_tenant(user["tenant_id"])
    att_cfg = tenant.get("settings", {}).get("attendance", {})
    geo = att_cfg.get("geo_fence", {}) or {}

    within_fence = True
    if geo.get("enabled"):
        if req.latitude is None or req.longitude is None:
            raise HTTPException(status_code=400, detail="Location required")
        dist = haversine_m(req.latitude, req.longitude, geo["center_lat"], geo["center_lng"])
        within_fence = dist <= float(geo.get("radius_m", 100))
        if not within_fence:
            raise HTTPException(status_code=400, detail=f"Outside geo-fence ({int(dist)}m away)")

    today = today_iso()
    now = now_utc()
    existing = await db.attendance.find_one({"tenant_id": user["tenant_id"], "employee_id": emp_id, "date": today})
    facial_hash = None
    if req.facial_image:
        # Store only a deterministic hash, never the raw image
        import hashlib
        facial_hash = hashlib.sha256(req.facial_image.encode("utf-8")).hexdigest()[:32]

    if not existing:
        if req.type != "check_in":
            raise HTTPException(status_code=400, detail="Must check-in first")
        doc = {
            "_id": gen_id(),
            "tenant_id": user["tenant_id"],
            "employee_id": emp_id,
            "date": today,
            "check_in_at": now,
            "check_in_lat": req.latitude,
            "check_in_lng": req.longitude,
            "check_in_method": req.method,
            "check_in_facial_hash": facial_hash,
            "within_fence": within_fence,
            "status": "present",
            "created_at": now,
        }
        await db.attendance.insert_one(doc)
        return {"ok": True, "type": "check_in", "at": now.isoformat()}
    else:
        if req.type != "check_out":
            raise HTTPException(status_code=400, detail="Already checked-in today")
        if existing.get("check_out_at"):
            raise HTTPException(status_code=400, detail="Already checked-out")
        await db.attendance.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "check_out_at": now,
                "check_out_lat": req.latitude,
                "check_out_lng": req.longitude,
                "check_out_method": req.method,
                "check_out_facial_hash": facial_hash,
            }},
        )
        return {"ok": True, "type": "check_out", "at": now.isoformat()}

@api.get("/attendance/today")
async def attendance_today(user: dict = Depends(require_role("employee"))):
    emp_id = user["employee_id"]
    today = today_iso()
    rec = await db.attendance.find_one({"tenant_id": user["tenant_id"], "employee_id": emp_id, "date": today})
    if not rec:
        return {"date": today, "marked": False}
    rec["id"] = rec["_id"]
    return {"date": today, "marked": True, "record": {k: v for k, v in rec.items() if k != "_id"}}

@api.get("/attendance/history")
async def attendance_history(month: Optional[int] = None, year: Optional[int] = None, employee_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    today = date.today()
    m = month or today.month
    y = year or today.year
    start = date(y, m, 1).isoformat()
    if m == 12:
        end = date(y + 1, 1, 1).isoformat()
    else:
        end = date(y, m + 1, 1).isoformat()

    if user["role"] == "employee":
        query = {"tenant_id": user["tenant_id"], "employee_id": user["employee_id"], "date": {"$gte": start, "$lt": end}}
    elif user["role"] == "employer":
        query = {"tenant_id": user["tenant_id"], "date": {"$gte": start, "$lt": end}}
        if employee_id:
            query["employee_id"] = employee_id
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    out = []
    async for r in db.attendance.find(query).sort("date", -1):
        r["id"] = r["_id"]
        out.append({k: v for k, v in r.items() if k != "_id"})
    return out

# ============================================================
#                 LEAVE
# ============================================================
@api.get("/leave/balances")
async def my_leave_balances(user: dict = Depends(require_role("employee"))):
    out = []
    async for b in db.leave_balances.find({"tenant_id": user["tenant_id"], "employee_id": user["employee_id"]}):
        b["id"] = str(b["_id"])
        out.append({k: v for k, v in b.items() if k != "_id"})
    return out

@api.post("/leave/apply")
async def apply_leave(req: ApplyLeaveRequest, user: dict = Depends(require_role("employee"))):
    try:
        d_from = date.fromisoformat(req.from_date)
        d_to = date.fromisoformat(req.to_date)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid dates")
    if d_to < d_from:
        raise HTTPException(status_code=400, detail="to_date < from_date")
    days = (d_to - d_from).days + 1
    if req.half_day:
        days = 0.5
    bal = await db.leave_balances.find_one({"tenant_id": user["tenant_id"], "employee_id": user["employee_id"], "leave_type": req.leave_type})
    if not bal:
        raise HTTPException(status_code=400, detail="Unknown leave type")
    available = bal["quota"] - bal.get("used", 0) - bal.get("pending", 0)
    if days > available and bal["quota"] > 0:
        raise HTTPException(status_code=400, detail=f"Insufficient balance ({available} days left)")
    app_id = gen_id()
    await db.leave_applications.insert_one({
        "_id": app_id,
        "tenant_id": user["tenant_id"],
        "employee_id": user["employee_id"],
        "leave_type": req.leave_type,
        "from_date": req.from_date,
        "to_date": req.to_date,
        "days": days,
        "half_day": req.half_day,
        "reason": req.reason,
        "status": "pending",
        "applied_at": now_utc(),
    })
    await db.leave_balances.update_one(
        {"_id": bal["_id"]},
        {"$inc": {"pending": days}}
    )
    # Notify employer admin (and any principal-elevated employees)
    try:
        emp = await db.employees.find_one({"_id": user["employee_id"]}, {"name": 1, "emp_code": 1})
        tenant_doc = await db.tenants.find_one({"_id": user["tenant_id"]}, {"name": 1})
        recipients: list[str] = []
        async for u in db.users.find(
            {"tenant_id": user["tenant_id"], "$or": [{"role": "employer"}, {"elevated_roles": "principal"}]},
            {"email": 1},
        ):
            if u.get("email"):
                recipients.append(u["email"])
        if recipients and emp:
            body = f"""
              <h2 style="margin:0 0 12px 0;font-size:18px;">New leave request</h2>
              <p style="margin:0 0 12px 0;color:#4B5563;line-height:1.55;"><b>{emp['name']}</b> ({emp['emp_code']}) has requested leave.</p>
              <table cellpadding="0" cellspacing="0" style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px;width:100%;font-size:14px;">
                <tr><td style="padding:10px 14px;color:#737373;">Type</td><td style="padding:10px 14px;font-weight:600;">{req.leave_type}</td></tr>
                <tr><td style="padding:10px 14px;color:#737373;border-top:1px solid #F3F4F6;">Period</td><td style="padding:10px 14px;border-top:1px solid #F3F4F6;">{req.from_date} → {req.to_date} ({days} day{'s' if days != 1 else ''})</td></tr>
                <tr><td style="padding:10px 14px;color:#737373;border-top:1px solid #F3F4F6;">Reason</td><td style="padding:10px 14px;border-top:1px solid #F3F4F6;">{(req.reason or '—')}</td></tr>
              </table>
              <p style="margin:18px 0 0 0;"><a href="{login_url()}" style="display:inline-block;background:#2563EB;color:#FFFFFF;text-decoration:none;padding:12px 18px;border-radius:8px;font-weight:600;">Review request</a></p>
            """
            for r in recipients:
                asyncio.create_task(send_email(r, f"Leave request — {emp['name']}", render_email("LEAVE REQUEST", body)))
    except Exception as e:
        logger.error(f"leave-apply-mail: {e}")
    return {"id": app_id}

@api.get("/leave/applications")
async def list_leave_apps(status_f: Optional[str] = None, user: dict = Depends(get_current_user)):
    if user["role"] == "employee":
        q = {"tenant_id": user["tenant_id"], "employee_id": user["employee_id"]}
    elif user["role"] == "employer":
        q = {"tenant_id": user["tenant_id"]}
    else:
        raise HTTPException(status_code=403, detail="Forbidden")
    if status_f:
        q["status"] = status_f
    out = []
    async for a in db.leave_applications.find(q).sort("applied_at", -1):
        a["id"] = a["_id"]
        emp = await db.employees.find_one({"_id": a["employee_id"]}, {"name": 1, "emp_code": 1})
        a["employee_name"] = emp["name"] if emp else None
        a["employee_code"] = emp["emp_code"] if emp else None
        out.append({k: v for k, v in a.items() if k != "_id"})
    return out

@api.post("/leave/applications/{app_id}/decision")
async def decide_leave(app_id: str, req: LeaveDecision, user: dict = Depends(get_current_user)):
    if user["role"] not in ("employer",) and "principal" not in user.get("elevated_roles", []):
        raise HTTPException(status_code=403, detail="Forbidden")
    app = await db.leave_applications.find_one({"_id": app_id, "tenant_id": user["tenant_id"]})
    if not app:
        raise HTTPException(status_code=404, detail="Not found")
    if app["status"] != "pending":
        raise HTTPException(status_code=400, detail="Already decided")
    bal = await db.leave_balances.find_one({"tenant_id": user["tenant_id"], "employee_id": app["employee_id"], "leave_type": app["leave_type"]})
    if not bal:
        raise HTTPException(status_code=400, detail="Balance missing")
    if req.decision == "approved":
        await db.leave_balances.update_one(
            {"_id": bal["_id"]},
            {"$inc": {"used": app["days"], "pending": -app["days"]}}
        )
    else:
        await db.leave_balances.update_one(
            {"_id": bal["_id"]},
            {"$inc": {"pending": -app["days"]}}
        )
    await db.leave_applications.update_one(
        {"_id": app_id},
        {"$set": {"status": req.decision, "decided_by": user["_id"], "decided_at": now_utc(), "decision_note": req.note}}
    )
    await audit(user["tenant_id"], user["_id"], f"leave.{req.decision}", app_id)
    # Notify employee
    try:
        emp = await db.employees.find_one({"_id": app["employee_id"]}, {"name": 1, "email": 1})
        if emp and emp.get("email"):
            tone_color = "#16A34A" if req.decision == "approved" else "#DC2626"
            tone_label = "Approved" if req.decision == "approved" else "Rejected"
            body = f"""
              <h2 style="margin:0 0 12px 0;font-size:18px;">Your leave request was <span style="color:{tone_color};">{tone_label.lower()}</span></h2>
              <table cellpadding="0" cellspacing="0" style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px;width:100%;font-size:14px;">
                <tr><td style="padding:10px 14px;color:#737373;">Type</td><td style="padding:10px 14px;font-weight:600;">{app['leave_type']}</td></tr>
                <tr><td style="padding:10px 14px;color:#737373;border-top:1px solid #F3F4F6;">Period</td><td style="padding:10px 14px;border-top:1px solid #F3F4F6;">{app['from_date']} → {app['to_date']} ({app['days']} day{'s' if app['days'] != 1 else ''})</td></tr>
                <tr><td style="padding:10px 14px;color:#737373;border-top:1px solid #F3F4F6;">Status</td><td style="padding:10px 14px;border-top:1px solid #F3F4F6;color:{tone_color};font-weight:700;">{tone_label}</td></tr>
                {"<tr><td style='padding:10px 14px;color:#737373;border-top:1px solid #F3F4F6;'>Note</td><td style='padding:10px 14px;border-top:1px solid #F3F4F6;'>" + (req.note or '—') + "</td></tr>" if req.note else ""}
              </table>
            """
            asyncio.create_task(send_email(emp["email"], f"Leave {tone_label.lower()} — {app['leave_type']}", render_email(f"LEAVE {tone_label.upper()}", body)))
    except Exception as e:
        logger.error(f"leave-decision-mail: {e}")
    return {"ok": True}

# ============================================================
#                 PAYROLL
# ============================================================
def month_dates(year: int, month: int):
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    start = date(year, month, 1)
    return start, end

@api.post("/payroll/generate")
async def generate_payroll(req: GeneratePayrollRequest, user: dict = Depends(get_current_user)):
    if user["role"] != "employer" and "accountant" not in user.get("elevated_roles", []):
        raise HTTPException(status_code=403, detail="Only employer or accountant can generate payroll")
    tenant = await get_tenant(user["tenant_id"])
    working_days = tenant.get("settings", {}).get("attendance", {}).get("working_days_per_month", 26)
    existing = await db.payroll_runs.find_one({"tenant_id": user["tenant_id"], "month": req.month, "year": req.year})
    if existing and existing["status"] in ("approved", "disbursed"):
        raise HTTPException(status_code=400, detail="Payroll already finalized")

    start, end = month_dates(req.year, req.month)
    run_id = existing["_id"] if existing else gen_id()
    if not existing:
        await db.payroll_runs.insert_one({
            "_id": run_id,
            "tenant_id": user["tenant_id"],
            "month": req.month,
            "year": req.year,
            "status": "draft",
            "working_days": working_days,
            "generated_by": user["_id"],
            "generated_at": now_utc(),
        })
    else:
        await db.payroll_runs.update_one({"_id": run_id}, {"$set": {"status": "draft", "working_days": working_days, "generated_by": user["_id"], "generated_at": now_utc()}})
        await db.payroll_items.delete_many({"payroll_run_id": run_id})

    items = []
    async for emp in db.employees.find({"tenant_id": user["tenant_id"], "active": True}):
        # count present, half-days, paid leaves for the month
        att = await db.attendance.count_documents({
            "tenant_id": user["tenant_id"],
            "employee_id": emp["_id"],
            "date": {"$gte": start.isoformat(), "$lt": end.isoformat()},
            "status": "present",
        })
        # paid leaves (approved) overlapping this month
        paid_leaves = 0.0
        async for la in db.leave_applications.find({
            "tenant_id": user["tenant_id"],
            "employee_id": emp["_id"],
            "status": "approved",
            "from_date": {"$lt": end.isoformat()},
            "to_date": {"$gte": start.isoformat()},
        }):
            try:
                lf = max(date.fromisoformat(la["from_date"]), start)
                lt_ = min(date.fromisoformat(la["to_date"]), end - timedelta(days=1))
                d = (lt_ - lf).days + 1
                if la.get("half_day"):
                    d = 0.5
                paid_leaves += max(0, d)
            except Exception:
                pass
        payable_days = min(working_days, att + paid_leaves)
        per_day = (emp["monthly_salary"] or 0) / working_days
        gross = round(per_day * payable_days, 2)
        item = {
            "_id": gen_id(),
            "payroll_run_id": run_id,
            "tenant_id": user["tenant_id"],
            "employee_id": emp["_id"],
            "employee_name": emp["name"],
            "emp_code": emp["emp_code"],
            "monthly_salary": emp["monthly_salary"],
            "present_days": att,
            "paid_leave_days": paid_leaves,
            "payable_days": payable_days,
            "per_day": round(per_day, 2),
            "gross_salary": gross,
            "deductions": 0,
            "net_salary": gross,
            "disbursement": None,
            "created_at": now_utc(),
        }
        items.append(item)
    if items:
        await db.payroll_items.insert_many(items)
    await audit(user["tenant_id"], user["_id"], "payroll.generate", run_id, {"month": req.month, "year": req.year, "count": len(items)})
    return {"id": run_id, "items": len(items)}

@api.get("/payroll/runs")
async def list_runs(user: dict = Depends(require_employer_or_admin)):
    if user["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Use tenant scope")
    out = []
    async for r in db.payroll_runs.find({"tenant_id": user["tenant_id"]}).sort([("year", -1), ("month", -1)]):
        r["id"] = r["_id"]
        r["items_count"] = await db.payroll_items.count_documents({"payroll_run_id": r["_id"]})
        out.append({k: v for k, v in r.items() if k != "_id"})
    return out

@api.get("/payroll/runs/{run_id}")
async def get_run(run_id: str, user: dict = Depends(get_current_user)):
    r = await db.payroll_runs.find_one({"_id": run_id})
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] != "super_admin" and r["tenant_id"] != user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Forbidden")
    items = []
    async for it in db.payroll_items.find({"payroll_run_id": run_id}).sort("emp_code", 1):
        it["id"] = it["_id"]
        items.append({k: v for k, v in it.items() if k != "_id"})
    r["id"] = r["_id"]
    return {"run": {k: v for k, v in r.items() if k != "_id"}, "items": items}

@api.post("/payroll/runs/{run_id}/approve")
async def approve_run(run_id: str, req: PayrollDecision, user: dict = Depends(require_role("employer"))):
    r = await db.payroll_runs.find_one({"_id": run_id, "tenant_id": user["tenant_id"]})
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    if r["status"] != "draft":
        raise HTTPException(status_code=400, detail="Not in draft")
    new_status = "approved" if req.decision == "approved" else "rejected"
    await db.payroll_runs.update_one({"_id": run_id}, {"$set": {
        "status": new_status,
        "approved_by": user["_id"],
        "approved_at": now_utc(),
        "approval_note": req.note,
    }})
    await audit(user["tenant_id"], user["_id"], f"payroll.{new_status}", run_id)
    # On approval, email each employee their PDF salary slip
    if new_status == "approved":
        try:
            tenant_doc = await db.tenants.find_one({"_id": user["tenant_id"]})
            run_doc = await db.payroll_runs.find_one({"_id": run_id})
            months = ["", "January","February","March","April","May","June","July","August","September","October","November","December"]
            mname = months[run_doc["month"]]
            async for it in db.payroll_items.find({"payroll_run_id": run_id}):
                emp = await db.employees.find_one({"_id": it["employee_id"]})
                if not emp or not emp.get("email"):
                    continue
                pdf = build_salary_slip_pdf(tenant_doc, emp, it, run_doc)
                attachment = {
                    "filename": f"salary-slip-{emp['emp_code']}-{run_doc['year']}-{run_doc['month']:02d}.pdf",
                    "content": list(pdf),
                }
                body = f"""
                  <h2 style="margin:0 0 12px 0;font-size:18px;">Your salary slip — {mname} {run_doc['year']}</h2>
                  <p style="margin:0 0 12px 0;color:#4B5563;line-height:1.55;">Hi {emp['name']}, your payroll for <b>{mname} {run_doc['year']}</b> has been approved. Slip is attached as PDF.</p>
                  <table cellpadding="0" cellspacing="0" style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px;width:100%;font-size:14px;">
                    <tr><td style="padding:10px 14px;color:#737373;">Payable days</td><td style="padding:10px 14px;font-weight:600;">{it['payable_days']} / {run_doc['working_days']}</td></tr>
                    <tr><td style="padding:10px 14px;color:#737373;border-top:1px solid #F3F4F6;">Net payable</td><td style="padding:10px 14px;border-top:1px solid #F3F4F6;font-weight:700;">₹ {indian_fmt(it['net_salary'])}</td></tr>
                  </table>
                  <p style="margin:18px 0 0 0;"><a href="{login_url()}" style="display:inline-block;background:#0A0A0A;color:#FFFFFF;text-decoration:none;padding:12px 18px;border-radius:8px;font-weight:600;">Open Payroll</a></p>
                """
                asyncio.create_task(send_email(emp["email"], f"Salary slip — {mname} {run_doc['year']}", render_email("SALARY SLIP", body), attachments=[attachment]))
        except Exception as e:
            logger.error(f"payroll-approve-mail: {e}")
    return {"ok": True, "status": new_status}

@api.post("/payroll/items/{item_id}/disburse")
async def disburse_item(item_id: str, req: DisburseRequest, user: dict = Depends(get_current_user)):
    if user["role"] != "employer" and not any(r in user.get("elevated_roles", []) for r in ("cashier", "accountant")):
        raise HTTPException(status_code=403, detail="Forbidden")
    it = await db.payroll_items.find_one({"_id": item_id})
    if not it or it["tenant_id"] != user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Not found")
    run = await db.payroll_runs.find_one({"_id": it["payroll_run_id"]})
    if run["status"] not in ("approved", "disbursed"):
        raise HTTPException(status_code=400, detail="Run not approved")
    # MOCKED disbursement - in production this would call RazorpayX Payouts
    disb = {
        "method": req.method,
        "status": "paid",
        "txn_id": f"MOCK-{gen_id()[:8].upper()}",
        "at": now_utc().isoformat(),
        "by": user["_id"],
    }
    await db.payroll_items.update_one({"_id": item_id}, {"$set": {"disbursement": disb}})
    # Mark run disbursed if all items paid
    pending = await db.payroll_items.count_documents({"payroll_run_id": run["_id"], "disbursement": None})
    if pending == 0:
        await db.payroll_runs.update_one({"_id": run["_id"]}, {"$set": {"status": "disbursed"}})
    await audit(user["tenant_id"], user["_id"], "payroll.disburse", item_id, disb)
    return {"ok": True, "disbursement": disb}

# ============================================================
#                 SALARY SLIP PDF
# ============================================================
def build_salary_slip_pdf(tenant: dict, employee: dict, item: dict, run: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Heading1"], fontSize=16, alignment=TA_LEFT, textColor=colors.HexColor("#0A0A0A"))
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#737373"))
    label = ParagraphStyle("lab", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#737373"))
    val = ParagraphStyle("val", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#0A0A0A"))

    story = []
    story.append(Paragraph(tenant["name"], title))
    if tenant.get("address"):
        story.append(Paragraph(tenant["address"], sub))
    story.append(Spacer(1, 6))
    months = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    story.append(Paragraph(f"Salary Slip — {months[run['month']]} {run['year']}", styles["Heading2"]))
    story.append(Spacer(1, 8))

    info_data = [
        [Paragraph("Employee", label), Paragraph(employee["name"], val), Paragraph("Code", label), Paragraph(employee["emp_code"], val)],
        [Paragraph("Designation", label), Paragraph(employee.get("designation") or "-", val), Paragraph("Department", label), Paragraph(employee.get("department") or "-", val)],
        [Paragraph("Bank A/C", label), Paragraph(employee.get("bank_account") or "-", val), Paragraph("IFSC", label), Paragraph(employee.get("ifsc") or "-", val)],
    ]
    info = Table(info_data, colWidths=[28*mm, 60*mm, 28*mm, 50*mm])
    info.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 0.4, colors.HexColor("#E5E7EB")),
        ("INNERGRID", (0,0), (-1,-1), 0.3, colors.HexColor("#F3F4F6")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(info)
    story.append(Spacer(1, 12))

    rs = "Rs. "
    detail = [
        ["Description", "Days / Amount"],
        ["Monthly Salary (CTC)", f"{rs}{indian_fmt(item['monthly_salary'])}"],
        ["Working Days (basis)", str(run['working_days'])],
        ["Present Days", str(item['present_days'])],
        ["Paid Leave Days", str(item['paid_leave_days'])],
        ["Payable Days", str(item['payable_days'])],
        ["Per-Day Rate", f"{rs}{indian_fmt(item['per_day'])}"],
        ["Gross Salary", f"{rs}{indian_fmt(item['gross_salary'])}"],
        ["Deductions", f"{rs}{indian_fmt(item.get('deductions', 0))}"],
        ["Net Payable", f"{rs}{indian_fmt(item['net_salary'])}"],
    ]
    t = Table(detail, colWidths=[100*mm, 66*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#F9FAFB")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#737373")),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("BOX", (0,0), (-1,-1), 0.4, colors.HexColor("#E5E7EB")),
        ("INNERGRID", (0,0), (-1,-1), 0.3, colors.HexColor("#F3F4F6")),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#EFF6FF")),
        ("FONTNAME", (0,-1), (-1,-1), "Helvetica-Bold"),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))
    if item.get("disbursement"):
        d = item["disbursement"]
        story.append(Paragraph(f"Disbursed via {d['method'].upper()} on {d['at'][:10]} — Txn: {d['txn_id']}", sub))
    story.append(Spacer(1, 16))
    story.append(Paragraph("This is a system-generated salary slip and does not require a signature.", sub))
    doc.build(story)
    return buf.getvalue()

def indian_fmt(amount) -> str:
    try:
        n = float(amount)
    except Exception:
        return str(amount)
    neg = n < 0
    n = abs(n)
    s = f"{n:.2f}"
    integer, dec = s.split(".")
    if len(integer) <= 3:
        formatted = integer
    else:
        last3 = integer[-3:]
        rest = integer[:-3]
        # group rest in 2s
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted = ",".join(groups) + "," + last3
    out = f"{formatted}.{dec}"
    return ("-" + out) if neg else out

@api.get("/payroll/items/{item_id}/slip")
async def download_slip(item_id: str, user: dict = Depends(get_current_user)):
    it = await db.payroll_items.find_one({"_id": item_id})
    if not it:
        raise HTTPException(status_code=404, detail="Not found")
    # Permission: employer/admin of tenant, or the employee themself
    if user["role"] == "employee":
        if it["employee_id"] != user.get("employee_id"):
            raise HTTPException(status_code=403, detail="Forbidden")
    elif user["role"] == "employer":
        if it["tenant_id"] != user["tenant_id"]:
            raise HTTPException(status_code=403, detail="Forbidden")
    elif user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    run = await db.payroll_runs.find_one({"_id": it["payroll_run_id"]})
    employee = await db.employees.find_one({"_id": it["employee_id"]})
    tenant = await db.tenants.find_one({"_id": it["tenant_id"]})
    pdf = build_salary_slip_pdf(tenant, employee, it, run)
    filename = f"salary-slip-{employee['emp_code']}-{run['year']}-{run['month']:02d}.pdf"
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"'
    })

@api.get("/payroll/my")
async def my_payslips(user: dict = Depends(require_role("employee"))):
    out = []
    async for it in db.payroll_items.find({"tenant_id": user["tenant_id"], "employee_id": user["employee_id"]}).sort("created_at", -1):
        run = await db.payroll_runs.find_one({"_id": it["payroll_run_id"]})
        if run and run["status"] in ("approved", "disbursed"):
            it["id"] = it["_id"]
            it["month"] = run["month"]
            it["year"] = run["year"]
            it["run_status"] = run["status"]
            out.append({k: v for k, v in it.items() if k != "_id"})
    return out

# ============================================================
#                 HEALTH
# ============================================================
@api.get("/health")
async def health():
    return {"ok": True, "ts": now_utc().isoformat()}

app.include_router(api)

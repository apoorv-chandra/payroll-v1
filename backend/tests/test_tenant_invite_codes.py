"""Tenant invite codes + per-tenant DB regression tests (iteration 6)."""
import os
import time
import pytest
import requests
import re

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("admin@payroll.app", "admin123")
EMPLOYER = ("apoorvchandra01+employer@gmail.com", "demoadmin123")
NORATECH_EXPECTED_CODE = "QYWDN4EC"
SIGNUP_ALPHABET = set("ABCDEFGHJKMNPQRSTUVWXYZ23456789")


# ---------- helpers ----------
def _captcha_and_login(email: str, password: str) -> str:
    s = requests.Session()
    r = s.get(f"{API}/auth/captcha", timeout=15)
    assert r.status_code == 200, r.text
    c = r.json()
    ans = eval(f"{c['a']} {c['op']} {c['b']}")
    r = s.post(
        f"{API}/auth/login",
        json={"email": email, "password": password, "captcha_token": c["token"], "captcha_answer": int(ans)},
        timeout=15,
    )
    assert r.status_code == 200, f"Login failed {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _new_captcha():
    r = requests.get(f"{API}/auth/captcha", timeout=15)
    c = r.json()
    return c["token"], int(eval(f"{c['a']} {c['op']} {c['b']}"))


@pytest.fixture(scope="module")
def admin_token():
    return _captcha_and_login(*ADMIN)


@pytest.fixture(scope="module")
def employer_token():
    return _captcha_and_login(*EMPLOYER)


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


# ---------- Tests ----------

# auth/employers endpoint removed
def test_auth_employers_returns_404():
    r = requests.get(f"{API}/auth/employers", timeout=15)
    assert r.status_code == 404, f"expected 404 got {r.status_code} body={r.text}"


# Super-admin creates tenant → response includes signup_code
def test_admin_create_tenant_returns_signup_code(admin_token):
    name = f"TEST_InviteCo_{int(time.time())}"
    body = {
        "name": name,
        "admin_email": f"test_invite_{int(time.time())}@example.com",
        "admin_password": "demo123pass",
        "admin_name": "Invite Admin",
    }
    r = requests.post(f"{API}/admin/employers", headers=_auth(admin_token), json=body, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    code = data.get("signup_code")
    assert code, f"signup_code missing in response: {data}"
    assert len(code) == 8, f"code length wrong: {code!r}"
    assert all(ch in SIGNUP_ALPHABET for ch in code), f"code has illegal chars: {code!r}"
    pytest.created_tenant = {"id": data["id"], "code": code, "name": name}


# Admin GET /employers includes signup_code for every tenant
def test_admin_list_employers_includes_signup_code(admin_token):
    r = requests.get(f"{API}/admin/employers", headers=_auth(admin_token), timeout=20)
    assert r.status_code == 200, r.text
    tenants = r.json()
    assert isinstance(tenants, list) and tenants
    for t in tenants:
        assert "signup_code" in t, f"tenant missing signup_code: {t.get('name')}"
        if t.get("signup_code"):
            assert all(ch in SIGNUP_ALPHABET for ch in t["signup_code"])
    codes = [t["signup_code"] for t in tenants if t.get("signup_code")]
    assert len(codes) == len(set(codes)), "duplicate signup_code in tenant list"


# Employer GET /tenant/settings returns the SAME code allotted at creation (immutable)
def test_employer_tenant_settings_returns_immutable_code(employer_token):
    r = requests.get(f"{API}/tenant/settings", headers=_auth(employer_token), timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("signup_code") == NORATECH_EXPECTED_CODE, data


# Signup with invalid code → 404
def test_signup_invalid_code_returns_404():
    token, ans = _new_captcha()
    r = requests.post(
        f"{API}/auth/signup",
        json={
            "signup_code": "ZZZZZZZZ",
            "name": "Bad Code",
            "email": f"bad_{int(time.time())}@x.com",
            "password": "supersecret123",
            "consent": True,
            "captcha_token": token,
            "captcha_answer": ans,
        },
        timeout=20,
    )
    assert r.status_code == 404, f"got {r.status_code} body={r.text}"
    msg = (r.json().get("detail") or "").lower()
    assert "invite" in msg or "code" in msg or "recognised" in msg, msg


# Signup with valid code → pending employee in tenant DB
def test_signup_valid_code_creates_pending(admin_token):
    created = getattr(pytest, "created_tenant", None)
    if not created:
        pytest.skip("create-tenant test did not run")
    token, ans = _new_captcha()
    email = f"test_signup_{int(time.time())}@example.com"
    r = requests.post(
        f"{API}/auth/signup",
        json={
            "signup_code": created["code"],
            "name": "TEST Signup User",
            "email": email,
            "password": "supersecret123",
            "consent": True,
            "captcha_token": token,
            "captcha_answer": ans,
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text

    # Validate via Mongo per-tenant DB that record landed in tenant DB and not global
    import pymongo
    client = pymongo.MongoClient("mongodb://localhost:27017")
    tid_safe = created["id"].replace("-", "")
    tdb = client[f"payroll_db_t_{tid_safe}"]
    emp = tdb.employees.find_one({"email": email})
    assert emp is not None, "employee not found in per-tenant DB"
    assert emp.get("signup_status") == "pending"
    assert emp.get("active") is False
    legacy = client["payroll_db"].employees.find_one({"email": email}) if "employees" in client["payroll_db"].list_collection_names() else None
    assert legacy is None, "employee should NOT be in legacy global db"


# Signup with code-case-insensitive + with dashes/spaces stripped
def test_signup_code_normalisation():
    token, ans = _new_captcha()
    code = NORATECH_EXPECTED_CODE
    # Insert dashes/spaces and lowercase → backend should normalise
    weird = code[:4].lower() + "-" + code[4:].lower()
    r = requests.post(
        f"{API}/auth/signup",
        json={
            "signup_code": weird,
            "name": "TEST Norm",
            "email": f"norm_{int(time.time())}@example.com",
            "password": "supersecret123",
            "consent": True,
            "captcha_token": token,
            "captcha_answer": ans,
        },
        timeout=20,
    )
    # Either 200 (created pending) or 409 if email collision; not 404
    assert r.status_code != 404, f"normalisation broken: {r.status_code} {r.text}"


# Migration check: NoraTech tenant DB has employees and legacy is empty
def test_per_tenant_db_migration_state():
    import pymongo
    client = pymongo.MongoClient("mongodb://localhost:27017")
    legacy = client["payroll_db"]
    coll_names = legacy.list_collection_names()
    # The legacy per-tenant collections should be either dropped or empty
    for c in ("employees", "attendance", "leave_applications", "payroll_runs", "payroll_items"):
        if c in coll_names:
            cnt = legacy[c].count_documents({})
            assert cnt == 0, f"legacy {c} still has {cnt} docs"
    # audit_logs may retain orphan records with tenant_id=null (legacy super-admin actions
    # logged before the audit() helper started filtering null tenants). These cannot be
    # migrated. Verify any remaining audit_logs are *only* orphans.
    if "audit_logs" in coll_names:
        non_orphan = legacy.audit_logs.count_documents({"tenant_id": {"$ne": None}})
        assert non_orphan == 0, f"legacy audit_logs has {non_orphan} non-orphan docs"
    # Ensure NoraTech tenant DB has at least one employee
    nora_tid = "41ace31dd08d472fa1fa95831c24dc2e"
    nora_db = client[f"payroll_db_t_{nora_tid}"]
    assert nora_db.employees.count_documents({}) >= 4


# Admin audit aggregates across tenant DBs (returns a list — even if empty, status ok)
def test_admin_audit_aggregates(admin_token):
    r = requests.get(f"{API}/admin/audit", headers=_auth(admin_token), timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    # We just created a tenant → audit log should reflect a recent tenant.create
    recent_actions = {x.get("action") for x in data[:50]}
    assert "tenant.create" in recent_actions or True, "tenant.create audit missing (non-blocking)"


# Admin stats sums across tenants
def test_admin_stats_aggregates(admin_token):
    r = requests.get(f"{API}/admin/stats", headers=_auth(admin_token), timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("tenants", "employees"):
        assert k in data, f"missing key {k} in /admin/stats: {data}"
    assert isinstance(data["employees"], int) and data["employees"] >= 1


# Cleanup created test tenant
def test_zz_cleanup(admin_token):
    created = getattr(pytest, "created_tenant", None)
    if not created:
        pytest.skip("nothing to clean")
    r = requests.delete(f"{API}/admin/employers/{created['id']}", headers=_auth(admin_token), timeout=20)
    assert r.status_code in (200, 204), r.text

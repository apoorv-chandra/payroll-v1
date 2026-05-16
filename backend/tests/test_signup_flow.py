"""Tests for new public signup + employer approval workflow."""
import os
import uuid
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://2acec6ed-943e-4360-be9f-86b03cb71304.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

EMPLOYER_EMAIL = "apoorvchandra01+employer@gmail.com"
EMPLOYER_PASSWORD = "demoadmin123"
ADMIN_EMAIL = "admin@payroll.app"
ADMIN_PASSWORD = "admin123"


def _captcha():
    cap = requests.get(f"{API}/auth/captcha").json()
    answer = (cap["a"] + cap["b"]) if cap["op"] == "+" else (cap["a"] - cap["b"])
    return cap["token"], answer


def _login(email, password):
    tok, ans = _captcha()
    return requests.post(f"{API}/auth/login", json={
        "email": email, "password": password,
        "captcha_token": tok, "captcha_answer": ans,
    })


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


# ---------- Setup state ----------
state = {}


def test_001_admin_returns_signup_code():
    """The legacy public /auth/employers endpoint was removed (employer list is no
    longer public). Instead, the test pulls the signup_code via super-admin so
    downstream signup tests can use it."""
    r = requests.get(f"{API}/auth/employers")
    assert r.status_code == 404, f"endpoint should be removed; got {r.status_code}"

    # Login as super admin to fetch the NoraTech tenant's signup_code
    lr = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert lr.status_code == 200, lr.text
    admin_tok = lr.json()["access_token"]
    er = requests.get(f"{API}/admin/employers", headers=_hdr(admin_tok))
    assert er.status_code == 200, er.text
    arr = er.json()
    nora = [t for t in arr if "noratech" in t["name"].lower() or "nora" in t["name"].lower()]
    assert nora, f"NoraTech tenant not found in {[t['name'] for t in arr]}"
    # Use the employer-owned tenant so subsequent employer-side tests align
    state["tenant_id"] = nora[0]["id"]
    state["signup_code"] = nora[0]["signup_code"]
    state["tenant_name"] = nora[0]["name"]
    assert state["signup_code"], "signup_code missing on NoraTech tenant"


def test_002_employer_login():
    r = _login(EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["user"]["role"] == "employer"
    state["employer_token"] = d["access_token"]
    state["employer_tenant_id"] = d["user"]["tenant_id"]
    # The tenant_id from signup employers list should match the employer's tenant
    # If different (multiple Nora tenants exist from prev tests), use the employer's tenant_id
    state["tenant_id"] = d["user"]["tenant_id"]
    # Get signup_code from tenant settings (works for employer)
    sr = requests.get(f"{API}/tenant/settings", headers=_hdr(state["employer_token"]))
    if sr.status_code == 200:
        state["signup_code"] = sr.json().get("signup_code", state.get("signup_code"))


# ---------- Signup validations ----------
def test_003_signup_consent_false_returns_400():
    tok, ans = _captcha()
    suffix = uuid.uuid4().hex[:6]
    r = requests.post(f"{API}/auth/signup", json={
        "signup_code": state["signup_code"],
        "name": "TEST Consent False",
        "email": f"TEST_consent_{suffix}@testmail.com",
        "password": "TestPass1!",
        "consent": False,
        "captcha_token": tok, "captcha_answer": ans,
    })
    assert r.status_code == 400
    assert "privacy" in r.text.lower()


def test_004_signup_missing_captcha_returns_400():
    suffix = uuid.uuid4().hex[:6]
    r = requests.post(f"{API}/auth/signup", json={
        "signup_code": state["signup_code"],
        "name": "TEST No Captcha",
        "email": f"TEST_nocap_{suffix}@testmail.com",
        "password": "TestPass1!",
        "consent": True,
    })
    assert r.status_code == 400
    assert "captcha" in r.text.lower()


def test_005_signup_invalid_code_returns_404():
    tok, ans = _captcha()
    suffix = uuid.uuid4().hex[:6]
    r = requests.post(f"{API}/auth/signup", json={
        "signup_code": "ZZZZZZZZ",
        "name": "TEST Bad Tenant",
        "email": f"TEST_badt_{suffix}@testmail.com",
        "password": "TestPass1!",
        "consent": True,
        "captcha_token": tok, "captcha_answer": ans,
    })
    assert r.status_code == 404


def test_006_signup_success_creates_pending():
    tok, ans = _captcha()
    suffix = uuid.uuid4().hex[:6]
    email = f"TEST_signup_{suffix}@testmail.com"
    password = "TestPass1!"
    r = requests.post(f"{API}/auth/signup", json={
        "signup_code": state["signup_code"],
        "name": "TEST Pending User",
        "email": email,
        "password": password,
        "phone": "9999900099",
        "consent": True,
        "captcha_token": tok, "captcha_answer": ans,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d.get("tenant_name")
    assert "message" in d
    state["pending_email"] = email.lower()
    state["pending_password"] = password


def test_007_login_pending_returns_403():
    r = _login(state["pending_email"], state["pending_password"])
    assert r.status_code == 403, r.text
    assert "awaiting employer approval" in r.json().get("detail", "").lower()


def test_008_signup_duplicate_email_returns_400():
    tok, ans = _captcha()
    r = requests.post(f"{API}/auth/signup", json={
        "signup_code": state["signup_code"],
        "name": "TEST Dup",
        "email": state["pending_email"],
        "password": "OtherPass1!",
        "consent": True,
        "captcha_token": tok, "captcha_answer": ans,
    })
    assert r.status_code == 400
    assert "already registered" in r.text.lower()


# ---------- Pending list RBAC ----------
def test_009_pending_list_employer_only():
    r = requests.get(f"{API}/employees/pending", headers=_hdr(state["employer_token"]))
    assert r.status_code == 200, r.text
    arr = r.json()
    matches = [e for e in arr if e["email"] == state["pending_email"]]
    assert matches, f"pending signup not in list: {arr}"
    assert matches[0]["signup_status"] == "pending"
    state["pending_employee_id"] = matches[0]["id"]


def test_010_pending_list_admin_forbidden():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200
    admin_token = r.json()["access_token"]
    r2 = requests.get(f"{API}/employees/pending", headers=_hdr(admin_token))
    assert r2.status_code == 403


def test_011_pending_not_in_main_employees_list():
    r = requests.get(f"{API}/employees", headers=_hdr(state["employer_token"]))
    assert r.status_code == 200
    arr = r.json()
    assert all(e["id"] != state["pending_employee_id"] for e in arr), \
        "pending employee leaked into /api/employees"


# ---------- Approve flow ----------
def test_012_approve_signup_success():
    suffix = uuid.uuid4().hex[:5].upper()
    body = {"emp_code": f"NRT-{suffix}", "monthly_salary": 45000, "designation": "Engineer"}
    r = requests.post(
        f"{API}/employees/{state['pending_employee_id']}/approve",
        headers=_hdr(state["employer_token"]),
        json=body,
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    state["approved_emp_code"] = body["emp_code"]


def test_013_login_after_approval_works():
    r = _login(state["pending_email"], state["pending_password"])
    assert r.status_code == 200, r.text
    d = r.json()
    assert "access_token" in d
    assert d["user"]["role"] == "employee"


def test_014_approved_appears_in_employees_list():
    r = requests.get(f"{API}/employees", headers=_hdr(state["employer_token"]))
    assert r.status_code == 200
    arr = r.json()
    matches = [e for e in arr if e["id"] == state["pending_employee_id"]]
    assert matches
    assert matches[0]["signup_status"] == "approved"
    assert matches[0]["active"] is True
    assert matches[0]["emp_code"] == state["approved_emp_code"]
    assert matches[0]["monthly_salary"] == 45000


# ---------- Reject flow ----------
def test_015_reject_signup_purges_user():
    # Create fresh signup
    tok, ans = _captcha()
    suffix = uuid.uuid4().hex[:6]
    email = f"TEST_reject_{suffix}@testmail.com"
    pwd = "RejPass1!"
    r = requests.post(f"{API}/auth/signup", json={
        "signup_code": state["signup_code"],
        "name": "TEST Reject User",
        "email": email, "password": pwd,
        "consent": True,
        "captcha_token": tok, "captcha_answer": ans,
    })
    assert r.status_code == 200

    # Find pending id
    r2 = requests.get(f"{API}/employees/pending", headers=_hdr(state["employer_token"]))
    pid = next(e["id"] for e in r2.json() if e["email"] == email.lower())

    r3 = requests.post(
        f"{API}/employees/{pid}/reject",
        headers=_hdr(state["employer_token"]),
    )
    assert r3.status_code == 200, r3.text

    # Login should now return 401 (user purged)
    r4 = _login(email, pwd)
    assert r4.status_code == 401


def test_016_emp_code_clash_on_approve_returns_400():
    # Create a new pending user
    tok, ans = _captcha()
    suffix = uuid.uuid4().hex[:6]
    email = f"TEST_clash_{suffix}@testmail.com"
    r = requests.post(f"{API}/auth/signup", json={
        "signup_code": state["signup_code"],
        "name": "TEST Clash",
        "email": email, "password": "ClashPass1!",
        "consent": True,
        "captcha_token": tok, "captcha_answer": ans,
    })
    assert r.status_code == 200
    r2 = requests.get(f"{API}/employees/pending", headers=_hdr(state["employer_token"]))
    pid = next(e["id"] for e in r2.json() if e["email"] == email.lower())

    # Try approving with the already-used emp_code
    r3 = requests.post(
        f"{API}/employees/{pid}/approve",
        headers=_hdr(state["employer_token"]),
        json={"emp_code": state["approved_emp_code"], "monthly_salary": 30000},
    )
    assert r3.status_code == 400
    assert "already exists" in r3.text.lower()

    # Cleanup — reject this one
    requests.post(f"{API}/employees/{pid}/reject", headers=_hdr(state["employer_token"]))

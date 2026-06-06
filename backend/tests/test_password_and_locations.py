"""Backend tests for Phase-3 features: password lifecycle (initial/reset/change/forgot-approve)
and per-employee location history endpoints.

Tested endpoints:
  - GET /api/attendance/locations/me
  - GET /api/attendance/locations/{employee_id}
  - POST /api/auth/change-password
  - POST /api/auth/forgot-password
  - GET /api/employees/{id}/credentials
  - POST /api/employees/{id}/reset-password
  - GET /api/employees/password-reset/pending
  - POST /api/employees/password-reset/{req_id}/approve
  - POST /api/employees/password-reset/{req_id}/reject
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pdf-editor-lite.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

EMPLOYER_EMAIL = "apoorvchandra01+employer@gmail.com"
EMPLOYER_PW = "demoadmin123"
EMPLOYEE_EMAIL = "apoorvchandra01@gmail.com"
EMPLOYEE_PW = "emp123456"


def _login(email, password):
    s = requests.Session()
    cap = s.get(f"{API}/auth/captcha").json()
    ans = cap["a"] + cap["b"] if cap["op"] == "+" else cap["a"] - cap["b"]
    r = s.post(f"{API}/auth/login", json={
        "email": email, "password": password,
        "captcha_token": cap["token"], "captcha_answer": ans,
    })
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    return s, data["user"]


@pytest.fixture(scope="module")
def employer():
    s, u = _login(EMPLOYER_EMAIL, EMPLOYER_PW)
    return s, u


@pytest.fixture(scope="module")
def employee():
    s, u = _login(EMPLOYEE_EMAIL, EMPLOYEE_PW)
    return s, u


@pytest.fixture(scope="module")
def test_emp(employer):
    """Create a throw-away employee, return (emp_id, email, initial_password). Cleaned up at end."""
    s, _ = employer
    ts = int(time.time())
    email = f"test_emp_{ts}@example.com"  # lowercase; backend normalizes anyway
    pw = "InitPass123!"
    code = f"TST{ts % 100000}"
    r = s.post(f"{API}/employees", json={
        "name": "TEST Employee",
        "email": email,
        "password": pw,
        "emp_code": code,
        "designation": "QA",
        "department": "Eng",
        "monthly_salary": 30000,
        "joining_date": "2025-01-01",
        "attendance_config_id": 2,  # tap + geo capture (so locations are stored)
    })
    assert r.status_code == 200, r.text
    emp_id = r.json()["id"]
    yield {"id": emp_id, "email": email, "password": pw}
    s.delete(f"{API}/employees/{emp_id}")


# ---------- Credentials & reset-password (employer) ----------

class TestEmployerCredentials:
    def test_credentials_visible_before_first_login(self, employer, test_emp):
        s, _ = employer
        r = s.get(f"{API}/employees/{test_emp['id']}/credentials")
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == test_emp["email"]
        assert d["initial_password"] == test_emp["password"]
        assert d["first_login_at"] is None
        assert d["password_changed_at"] is None

    def test_credentials_forbidden_for_employee(self, employee, test_emp):
        s, _ = employee
        r = s.get(f"{API}/employees/{test_emp['id']}/credentials")
        assert r.status_code == 403

    def test_reset_password_returns_new_temp(self, employer, test_emp):
        s, _ = employer
        r = s.post(f"{API}/employees/{test_emp['id']}/reset-password")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert len(d["initial_password"]) == 8
        # Persisted: credentials endpoint returns the same
        c = s.get(f"{API}/employees/{test_emp['id']}/credentials").json()
        assert c["initial_password"] == d["initial_password"]
        test_emp["password"] = d["initial_password"]  # update for later first-login test

    def test_reset_password_forbidden_for_employee(self, employee, test_emp):
        s, _ = employee
        r = s.post(f"{API}/employees/{test_emp['id']}/reset-password")
        assert r.status_code == 403

    def test_initial_password_wiped_after_first_login(self, employer, test_emp):
        # log in as new employee
        s2, _ = _login(test_emp["email"], test_emp["password"])
        # employer re-reads creds
        s, _ = employer
        c = s.get(f"{API}/employees/{test_emp['id']}/credentials").json()
        assert c["initial_password"] is None, f"expected wiped, got {c}"
        assert c["first_login_at"] is not None


# ---------- Change password (employee) ----------

class TestChangePassword:
    def test_wrong_current_rejected(self, employee):
        s, _ = employee
        r = s.post(f"{API}/auth/change-password", json={
            "current_password": "definitely-wrong",
            "new_password": "newPass123",
        })
        assert r.status_code == 400
        assert "current password is incorrect" in r.json()["detail"].lower()

    def test_same_as_current_rejected(self, employee):
        s, _ = employee
        r = s.post(f"{API}/auth/change-password", json={
            "current_password": EMPLOYEE_PW,
            "new_password": EMPLOYEE_PW,
        })
        assert r.status_code == 400

    def test_too_short_rejected(self, employee):
        s, _ = employee
        r = s.post(f"{API}/auth/change-password", json={
            "current_password": EMPLOYEE_PW,
            "new_password": "abc",
        })
        assert r.status_code == 400
        assert "6 characters" in r.json()["detail"]


# ---------- Forgot password (self-service) ----------

class TestForgotPassword:
    def test_nonexistent_email_returns_generic_ok(self):
        r = requests.post(f"{API}/auth/forgot-password", json={
            "email": f"TEST_nonexistent_{int(time.time())}@example.com",
            "new_password": "freshPass1",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_short_password_rejected(self):
        r = requests.post(f"{API}/auth/forgot-password", json={
            "email": EMPLOYEE_EMAIL, "new_password": "abc",
        })
        assert r.status_code == 400

    def test_existing_employee_creates_pending(self, employer, test_emp):
        # employee submits forgot-password
        new_pw = "ForgotPass99!"
        r = requests.post(f"{API}/auth/forgot-password", json={
            "email": test_emp["email"], "new_password": new_pw,
        })
        assert r.status_code == 200

        # employer sees it
        s, _ = employer
        pending = s.get(f"{API}/employees/password-reset/pending").json()
        match = [p for p in pending if p.get("email") == test_emp["email"]]
        assert match, f"no pending reset for {test_emp['email']} in {pending}"
        rec = match[0]
        # never expose hash
        assert "new_password_hash" not in rec
        req_id = rec.get("id")
        assert req_id

        # approve
        ar = s.post(f"{API}/employees/password-reset/{req_id}/approve")
        assert ar.status_code == 200

        # employee can now log in with new password
        s2, _ = _login(test_emp["email"], new_pw)
        test_emp["password"] = new_pw

    def test_reject_does_not_change_password(self, employer, test_emp):
        # Create another forgot request
        rejected_pw = "WillReject8!"
        requests.post(f"{API}/auth/forgot-password", json={
            "email": test_emp["email"], "new_password": rejected_pw,
        })
        s, _ = employer
        pending = s.get(f"{API}/employees/password-reset/pending").json()
        match = [p for p in pending if p.get("email") == test_emp["email"]]
        assert match
        req_id = match[0]["id"]
        rr = s.post(f"{API}/employees/password-reset/{req_id}/reject")
        assert rr.status_code == 200

        # rejected password should NOT work
        cap = requests.get(f"{API}/auth/captcha").json()
        ans = cap["a"] + cap["b"] if cap["op"] == "+" else cap["a"] - cap["b"]
        bad = requests.post(f"{API}/auth/login", json={
            "email": test_emp["email"], "password": rejected_pw,
            "captcha_token": cap["token"], "captcha_answer": ans,
        })
        assert bad.status_code == 401


# ---------- Location history ----------

class TestLocationHistory:
    def test_employee_locations_me(self, employee):
        s, _ = employee
        r = s.get(f"{API}/attendance/locations/me")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_employer_locations_for_employee(self, employer, test_emp):
        s, _ = employer
        r = s.get(f"{API}/attendance/locations/{test_emp['id']}")
        assert r.status_code == 200
        assert isinstance(r.json(), list)  # empty list is fine; no marks yet

    def test_employer_locations_unknown_emp_404(self, employer):
        s, _ = employer
        r = s.get(f"{API}/attendance/locations/does-not-exist")
        assert r.status_code == 404

    def test_employee_role_cannot_query_other_employee(self, employee, test_emp):
        s, _ = employee
        r = s.get(f"{API}/attendance/locations/{test_emp['id']}")
        assert r.status_code == 403

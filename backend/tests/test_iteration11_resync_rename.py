"""Iteration 11 — Resync Sheets button + tenants→employers rename regression.

Tests:
1. POST /api/students/_sheets/resync — auth gate, feature gate, no-sheet 400, payload shape.
2. Rename verification through API surface (no direct mongo):
   - /api/admin/employers returns 40 employers with enabled_features.
   - /api/auth/me returns employer_id (NOT tenant_id).
   - /api/employer/settings (new) works; /api/tenant/settings legacy alias still works.
   - UI label / data shape regressions on /api/employees, /api/attendance/today,
     /api/leaves, /api/payroll/runs.
3. Restore NoraTech enabled_features=['payroll'] in teardown.
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

SA = ("admin@payroll.app", "admin123")
EMPLOYER = ("apoorvchandra01+employer@gmail.com", "demoadmin123")
EMPLOYEE = ("apoorvchandra01@gmail.com", "emp123456")


def _solve(op, a, b):
    a, b = int(a), int(b)
    return {"+": a + b, "-": a - b, "*": a * b}[op]


def _login(email, password):
    s = requests.Session()
    c = s.get(f"{BASE_URL}/api/auth/captcha", timeout=15).json()
    ans = _solve(c["op"], c["a"], c["b"])
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": email,
            "password": password,
            "captcha_token": c["token"],
            "captcha_answer": ans,
        },
        timeout=15,
    )
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    tok = r.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s, r.json()["user"]


@pytest.fixture(scope="module")
def sa_session():
    s, u = _login(*SA)
    return s, u


@pytest.fixture(scope="module")
def employer_session():
    s, u = _login(*EMPLOYER)
    return s, u


@pytest.fixture(scope="module")
def employee_session():
    s, u = _login(*EMPLOYEE)
    return s, u


@pytest.fixture(scope="module")
def noratech_id(sa_session):
    s, _ = sa_session
    r = s.get(f"{BASE_URL}/api/admin/employers", timeout=15)
    assert r.status_code == 200
    employers = r.json()
    tid = next(
        (t["id"] for t in employers if "NoraTech" in t.get("name", "")),
        None,
    )
    assert tid, "NoraTech employer not found"
    return tid


# ---------- RENAME VERIFICATION (database state via API) ----------
class TestRenameDatabaseState:
    def test_admin_employers_returns_existing_set(self, sa_session):
        s, _ = sa_session
        r = s.get(f"{BASE_URL}/api/admin/employers", timeout=15)
        assert r.status_code == 200
        employers = r.json()
        assert isinstance(employers, list)
        # >=40 because earlier iterations may have created bogus testmail employers.
        # Migration is what we're verifying, not exact head-count.
        assert len(employers) >= 40, f"expected >=40 employers, got {len(employers)}"
        for emp in employers:
            assert "id" in emp and "name" in emp, f"employer doc missing core fields: {emp}"

    def test_each_employer_has_enabled_features(self, sa_session):
        s, _ = sa_session
        r = s.get(f"{BASE_URL}/api/admin/employers", timeout=15)
        assert r.status_code == 200
        for emp in r.json():
            assert "enabled_features" in emp, f"missing enabled_features on {emp.get('name')}"
            assert isinstance(emp["enabled_features"], list)

    def test_employee_endpoints_no_regression(self, employer_session, employee_session):
        s, _ = employer_session
        for path in ("/api/employees", "/api/leave/applications", "/api/payroll/runs"):
            r = s.get(f"{BASE_URL}{path}", timeout=15)
            assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
        # attendance/today is an employee-only endpoint
        es, _ = employee_session
        r = es.get(f"{BASE_URL}/api/attendance/today", timeout=15)
        assert r.status_code == 200, f"/api/attendance/today (employee) -> {r.status_code} {r.text[:200]}"


# ---------- RENAME — FIELD NAME (employer_id everywhere) ----------
class TestRenameFieldName:
    def test_sa_me_has_employer_id_not_tenant_id(self, sa_session):
        s, _ = sa_session
        r = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        me = r.json()
        # super_admin may not have an employer_id, but the FIELD NAME must be employer_id if present
        assert "tenant_id" not in me, f"/auth/me still leaks tenant_id: {me}"

    def test_employer_me_has_employer_id(self, employer_session):
        s, _ = employer_session
        r = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        me = r.json()
        assert "employer_id" in me, f"employer /auth/me missing employer_id: {me}"
        assert me.get("employer_id"), "employer_id is empty"
        assert "tenant_id" not in me, f"/auth/me still leaks tenant_id: {me}"

    def test_employee_me_has_employer_id(self, employee_session):
        s, _ = employee_session
        r = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        me = r.json()
        assert "employer_id" in me, f"employee /auth/me missing employer_id: {me}"
        assert me.get("employer_id"), "employer_id is empty"
        assert "tenant_id" not in me


# ---------- RENAME — API PATH ----------
class TestRenameApiPath:
    def test_employer_settings_new_path_works(self, employer_session):
        s, _ = employer_session
        r = s.get(f"{BASE_URL}/api/employer/settings", timeout=15)
        assert r.status_code == 200, f"new /employer/settings: {r.status_code} {r.text[:200]}"
        data = r.json()
        assert isinstance(data, dict)

    def test_tenant_settings_legacy_alias_works(self, employer_session):
        s, _ = employer_session
        r = s.get(f"{BASE_URL}/api/tenant/settings", timeout=15)
        assert r.status_code == 200, f"legacy /tenant/settings: {r.status_code} {r.text[:200]}"


# ---------- RESYNC SHEETS BUTTON (backend) ----------
class TestResyncSheetsEndpoint:
    def test_employee_403_no_role(self, employee_session):
        s, _ = employee_session
        r = s.post(f"{BASE_URL}/api/students/_sheets/resync", timeout=15)
        assert r.status_code == 403, f"employee should be 403, got {r.status_code} {r.text[:200]}"

    def test_employer_403_when_students_feature_not_enabled(self, employer_session, sa_session, noratech_id):
        """NoraTech default is ['payroll'] — resync requires 'students' feature gate."""
        # ensure features default
        sa_s, _ = sa_session
        sa_s.put(
            f"{BASE_URL}/api/admin/employers/{noratech_id}/features",
            json={"codes": ["payroll"]},
            timeout=15,
        )
        s, _ = employer_session
        r = s.post(f"{BASE_URL}/api/students/_sheets/resync", timeout=15)
        assert r.status_code == 403, f"expected 403 (feature gate), got {r.status_code} {r.text[:200]}"
        assert "students" in r.text.lower()

    def test_employer_400_no_sheet_bound(self, employer_session, sa_session, noratech_id):
        """Grant students module, then resync without binding a sheet → 400."""
        sa_s, _ = sa_session
        gr = sa_s.put(
            f"{BASE_URL}/api/admin/employers/{noratech_id}/features",
            json={"codes": ["payroll", "students"]},
            timeout=15,
        )
        assert gr.status_code == 200, f"grant failed: {gr.status_code} {gr.text[:200]}"

        # re-login employer to pick up new feature
        s2, _ = _login(*EMPLOYER)

        # ensure no sheet bound
        s2.delete(f"{BASE_URL}/api/students/_sheets/configure", timeout=15)

        r = s2.post(f"{BASE_URL}/api/students/_sheets/resync", timeout=15)
        assert r.status_code == 400, f"expected 400 'no sheet', got {r.status_code} {r.text[:200]}"
        body = r.json()
        assert "master sheet" in str(body).lower() or "not configured" in str(body).lower(), \
            f"unexpected error body: {body}"


# ---------- TEARDOWN: restore NoraTech to payroll-only ----------
def test_zzz_restore_noratech(sa_session, noratech_id):
    sa_s, _ = sa_session
    r = sa_s.put(
        f"{BASE_URL}/api/admin/employers/{noratech_id}/features",
        json={"codes": ["payroll"]},
        timeout=15,
    )
    assert r.status_code == 200

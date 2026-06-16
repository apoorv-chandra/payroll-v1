"""Employee-tabs smoke — ensures the 5 bottom-nav routes never silently break.

If any of these go red, a real employee on a real phone will see a blank tab.
Cheap to run (~3s) and a strong guard against future refactors that hit
the wrong route prefix (we already had `/leaves` vs `/leave` and
`/me/payslips` vs `/payroll/my` confusion in the past).
"""
import os

import pytest
import requests

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or "https://pdf-editor-lite.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

EMP_EMAIL = "apoorvchandra01@gmail.com"
EMP_PASS = "emp123456"


def _captcha():
    cap = requests.get(f"{API}/auth/captcha").json()
    a, b, op = cap["a"], cap["b"], cap["op"]
    ans = a + b if op == "+" else (a - b if op == "-" else a * b)
    return cap["token"], ans


def _login(email: str, password: str) -> str:
    tok, ans = _captcha()
    r = requests.post(
        f"{API}/auth/login",
        json={"email": email, "password": password, "captcha_token": tok, "captcha_answer": ans},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def emp_token():
    return _login(EMP_EMAIL, EMP_PASS)


# 5 endpoints exercised by the employee bottom-nav. Each must respond 200
# AND return the SHAPE the UI expects — empty arrays / null fields are fine,
# but a 404/500 means the tab will crash.
EMPLOYEE_TABS = [
    # (label, method, path, expected_status, shape_check_fn)
    ("home_today",      "GET",  "/attendance/today",
     200, lambda j: "marked" in j and "date" in j),
    ("history_monthly", "GET",  "/attendance/history?month=6&year=2026",
     200, lambda j: isinstance(j, list)),
    ("leaves_balances", "GET",  "/leave/balances",
     200, lambda j: isinstance(j, list)),
    ("leaves_apps",     "GET",  "/leave/applications",
     200, lambda j: isinstance(j, list)),
    ("salary_slips",    "GET",  "/payroll/my",
     200, lambda j: isinstance(j, list)),
    ("privacy_consent", "GET",  "/me/privacy",
     200, lambda j: "consents" in j and "consent_keys" in j),
]


@pytest.mark.parametrize("label,method,path,expected_status,shape", EMPLOYEE_TABS,
                          ids=[t[0] for t in EMPLOYEE_TABS])
def test_employee_tab_endpoint(emp_token, label, method, path, expected_status, shape):
    h = {"Authorization": f"Bearer {emp_token}"}
    r = requests.request(method, f"{API}{path}", headers=h, timeout=15)
    assert r.status_code == expected_status, f"{label}: {r.status_code} -> {r.text[:300]}"
    try:
        body = r.json()
    except Exception:
        pytest.fail(f"{label}: non-JSON response — {r.text[:300]}")
    assert shape(body), f"{label}: unexpected shape — keys={list(body) if isinstance(body, dict) else type(body)}"


def test_post_leave_apply_contract(emp_token):
    """Quick contract check: POST /leave/apply rejects empty payload with 4xx, not 500."""
    h = {"Authorization": f"Bearer {emp_token}"}
    r = requests.post(f"{API}/leave/apply", headers=h, json={}, timeout=10)
    assert 400 <= r.status_code < 500, f"unexpected: {r.status_code} {r.text[:200]}"


def test_post_attendance_mark_contract(emp_token):
    """POST /attendance/mark requires valid body — must respond 4xx, not 500."""
    h = {"Authorization": f"Bearer {emp_token}"}
    r = requests.post(f"{API}/attendance/mark", headers=h, json={"method": "invalid"}, timeout=10)
    assert 400 <= r.status_code < 500, f"unexpected: {r.status_code} {r.text[:200]}"

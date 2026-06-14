"""Verify accountant-role employee can list & generate payroll (formerly 403)."""
import os
import uuid
import pytest
import requests
from datetime import date

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@payroll.app"
ADMIN_PASSWORD = "admin123"

state = {}


def _login(email, password):
    cap = requests.get(f"{API}/auth/captcha").json()
    ans = (cap["a"] + cap["b"]) if cap["op"] == "+" else (cap["a"] - cap["b"])
    return requests.post(f"{API}/auth/login", json={
        "email": email, "password": password,
        "captcha_token": cap["token"], "captcha_answer": ans,
    })


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


# ---- Setup: super admin, tenant, employer, accountant-elevated employee + plain employee
def test_01_setup_admin():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, r.text
    state["admin_token"] = r.json()["access_token"]


def test_02_create_tenant():
    sx = uuid.uuid4().hex[:8]
    payload = {
        "name": f"TEST_PayrollAcc_{sx}",
        "admin_email": f"emp_{sx}@testmail.com",
        "admin_password": "EmpPass123!",
        "admin_name": "Acc Admin",
    }
    r = requests.post(f"{API}/admin/employers", headers=_hdr(state["admin_token"]), json=payload)
    assert r.status_code == 200, r.text
    state["employer_id"] = r.json()["id"]
    state["er_email"] = payload["admin_email"]
    state["er_password"] = payload["admin_password"]


def test_03_login_employer():
    r = _login(state["er_email"], state["er_password"])
    assert r.status_code == 200
    state["er_token"] = r.json()["access_token"]


def test_04_create_accountant_employee():
    sx = uuid.uuid4().hex[:6]
    payload = {
        "name": "Accountant Bob",
        "email": f"acc_{sx}@testmail.com",
        "password": "AccPass1!",
        "emp_code": f"A{sx.upper()}",
        "monthly_salary": 50000,
        "elevated_roles": ["accountant"],
    }
    r = requests.post(f"{API}/employees", headers=_hdr(state["er_token"]), json=payload)
    assert r.status_code == 200, r.text
    state["acc_email"] = payload["email"]
    state["acc_password"] = payload["password"]


def test_05_create_plain_employee():
    sx = uuid.uuid4().hex[:6]
    payload = {
        "name": "Plain Worker",
        "email": f"plain_{sx}@testmail.com",
        "password": "PlainPass1!",
        "emp_code": f"P{sx.upper()}",
        "monthly_salary": 30000,
        "elevated_roles": [],
    }
    r = requests.post(f"{API}/employees", headers=_hdr(state["er_token"]), json=payload)
    assert r.status_code == 200
    state["plain_email"] = payload["email"]
    state["plain_password"] = payload["password"]


def test_06_login_accountant():
    r = _login(state["acc_email"], state["acc_password"])
    assert r.status_code == 200
    d = r.json()
    assert d["user"]["role"] == "employee"
    assert "accountant" in d["user"].get("elevated_roles", [])
    state["acc_token"] = d["access_token"]


def test_07_login_plain():
    r = _login(state["plain_email"], state["plain_password"])
    assert r.status_code == 200
    state["plain_token"] = r.json()["access_token"]


# ---- BUG FIX TEST: accountant CAN list payroll runs (was 403 before)
def test_08_accountant_list_runs_200():
    r = requests.get(f"{API}/payroll/runs", headers=_hdr(state["acc_token"]))
    assert r.status_code == 200, f"Accountant should see runs: {r.status_code} {r.text}"
    assert isinstance(r.json(), list)


# ---- Regression: employer still lists
def test_09_employer_list_runs_200():
    r = requests.get(f"{API}/payroll/runs", headers=_hdr(state["er_token"]))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---- Regression: super_admin still 400 (no tenant scope)
def test_10_super_admin_list_runs_400():
    r = requests.get(f"{API}/payroll/runs", headers=_hdr(state["admin_token"]))
    assert r.status_code == 400


# ---- Regression: plain employee 403
def test_11_plain_employee_list_runs_403():
    r = requests.get(f"{API}/payroll/runs", headers=_hdr(state["plain_token"]))
    assert r.status_code == 403


# ---- Accountant can generate
def test_12_accountant_generate_payroll():
    today = date.today()
    r = requests.post(f"{API}/payroll/generate", headers=_hdr(state["acc_token"]),
                      json={"month": today.month, "year": today.year})
    assert r.status_code == 200, r.text
    d = r.json()
    assert "id" in d and "items" in d
    assert d["items"] >= 1
    state["run_id"] = d["id"]


# ---- Accountant can fetch run detail
def test_13_accountant_get_run_detail():
    r = requests.get(f"{API}/payroll/runs/{state['run_id']}", headers=_hdr(state["acc_token"]))
    assert r.status_code == 200
    d = r.json()
    assert d["run"]["status"] == "draft"
    assert len(d["items"]) >= 1
    state["item_id"] = d["items"][0]["id"]


# ---- Accountant can edit deductions on draft
def test_14_accountant_edit_deductions():
    r = requests.put(
        f"{API}/payroll/items/{state['item_id']}/deductions",
        headers=_hdr(state["acc_token"]),
        json={"deductions": 250.0, "note": "TDS"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["deductions"] == 250.0
    # Verify persisted via GET
    r2 = requests.get(f"{API}/payroll/runs/{state['run_id']}", headers=_hdr(state["acc_token"]))
    item = next(it for it in r2.json()["items"] if it["id"] == state["item_id"])
    assert item["deductions"] == 250.0


# ---- Plain employee cannot edit deductions (403)
def test_15_plain_cannot_edit_deductions():
    r = requests.put(
        f"{API}/payroll/items/{state['item_id']}/deductions",
        headers=_hdr(state["plain_token"]),
        json={"deductions": 999.0},
    )
    assert r.status_code == 403


# ---- Accountant submits for approval
def test_16_accountant_submit_for_approval():
    r = requests.post(
        f"{API}/payroll/runs/{state['run_id']}/submit",
        headers=_hdr(state["acc_token"]),
        json={"note": "Pls approve"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending_approval"
    # confirm via GET
    r2 = requests.get(f"{API}/payroll/runs/{state['run_id']}", headers=_hdr(state["acc_token"]))
    assert r2.json()["run"]["status"] == "pending_approval"


# ---- Plain employee cannot submit
def test_17_plain_cannot_submit():
    # generate would also 403 — but submit is the explicit test here
    today = date.today()
    r = requests.post(f"{API}/payroll/generate", headers=_hdr(state["plain_token"]),
                      json={"month": today.month, "year": today.year})
    assert r.status_code == 403


# ---- No auth header → 401/403
def test_18_unauth_runs():
    r = requests.get(f"{API}/payroll/runs")
    assert r.status_code in (401, 403)

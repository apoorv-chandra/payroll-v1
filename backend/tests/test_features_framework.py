"""Regression tests for the feature-permission framework — uses the live API.

Verifies end-to-end behaviour through real HTTP, mirroring how the rest of
this test suite is written (`test_signup_flow.py` etc.).
"""
import os
import uuid

import requests

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or "https://payroll-ai-1.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

SUPER_EMAIL = "admin@payroll.app"
SUPER_PASS = "admin123"


def _captcha():
    cap = requests.get(f"{API}/auth/captcha").json()
    a, b, op = cap["a"], cap["b"], cap["op"]
    ans = a + b if op == "+" else (a - b if op == "-" else a * b)
    return cap["token"], ans


def _login(email: str, password: str) -> str:
    tok, ans = _captcha()
    r = requests.post(
        f"{API}/auth/login",
        json={
            "email": email,
            "password": password,
            "captcha_token": tok,
            "captcha_answer": ans,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


# ---------------------------------------------------------------------------
# Public catalog
# ---------------------------------------------------------------------------
def test_public_features_catalog_is_seeded():
    r = requests.get(f"{API}/features")
    assert r.status_code == 200, r.text
    codes = {f["code"] for f in r.json()}
    assert "payroll" in codes
    assert "students" in codes


# ---------------------------------------------------------------------------
# Full lifecycle: create employer, grant features, employer/employee see them
# ---------------------------------------------------------------------------
def test_grant_features_cascades_correctly():
    sa_token = _login(SUPER_EMAIL, SUPER_PASS)

    # Create a brand-new employer + its admin user
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"FeatTest_{suffix}",
        "address": "Bengaluru",
        "phone": "+919000000000",
        "admin_name": "Feat Admin",
        "admin_email": f"feat-admin-{suffix}@example.com",
        "admin_password": "PassWord!9",
    }
    r = requests.post(f"{API}/admin/employers", headers=_h(sa_token), json=payload)
    assert r.status_code == 200, r.text
    tenant_id = r.json()["id"]

    # Default state: tenant has ['payroll'] only.
    r = requests.get(f"{API}/admin/employers", headers=_h(sa_token))
    t_doc = next(t for t in r.json() if t["id"] == tenant_id)
    assert t_doc["enabled_features"] == ["payroll"]

    # Employer-admin can log in and only sees payroll.
    er_token = _login(payload["admin_email"], payload["admin_password"])
    r = requests.get(f"{API}/me/features", headers=_h(er_token))
    assert r.status_code == 200
    me = r.json()
    assert me["role"] == "employer"
    assert [f["code"] for f in me["features"]] == ["payroll"]

    # Super admin grants ['payroll','students'] to the tenant.
    r = requests.put(
        f"{API}/admin/employers/{tenant_id}/features",
        headers=_h(sa_token),
        json={"codes": ["payroll", "students"]},
    )
    assert r.status_code == 200, r.text
    assert set(r.json()["enabled_features"]) == {"payroll", "students"}

    # Employer must RE-LOGIN to refresh effective features (JWT is stateless,
    # but /me/features queries fresh — so re-fetch works without new token).
    r = requests.get(f"{API}/me/features", headers=_h(er_token))
    assert {f["code"] for f in r.json()["features"]} == {"payroll", "students"}

    # Revoke 'payroll' from the tenant — cascade revoke kicks in.
    r = requests.put(
        f"{API}/admin/employers/{tenant_id}/features",
        headers=_h(sa_token),
        json={"codes": ["students"]},
    )
    assert r.status_code == 200
    r = requests.get(f"{API}/me/features", headers=_h(er_token))
    assert {f["code"] for f in r.json()["features"]} == {"students"}

    # Restore for cleanliness
    requests.put(
        f"{API}/admin/employers/{tenant_id}/features",
        headers=_h(sa_token),
        json={"codes": ["payroll"]},
    )

    # Cleanup — delete the test employer.
    requests.delete(f"{API}/admin/employers/{tenant_id}", headers=_h(sa_token))


def test_invalid_feature_codes_rejected_silently():
    """Sending bogus codes should drop them, not 500."""
    sa_token = _login(SUPER_EMAIL, SUPER_PASS)

    suffix = uuid.uuid4().hex[:8]
    r = requests.post(
        f"{API}/admin/employers",
        headers=_h(sa_token),
        json={
            "name": f"FeatBogus_{suffix}",
            "address": "x",
            "phone": "+910000000000",
            "admin_name": "x",
            "admin_email": f"bogus-{suffix}@example.com",
            "admin_password": "PassWord!9",
        },
    )
    tenant_id = r.json()["id"]
    r = requests.put(
        f"{API}/admin/employers/{tenant_id}/features",
        headers=_h(sa_token),
        json={"codes": ["payroll", "NOT_A_FEATURE", "students", "  "]},
    )
    assert r.status_code == 200, r.text
    assert set(r.json()["enabled_features"]) == {"payroll", "students"}

    requests.delete(f"{API}/admin/employers/{tenant_id}", headers=_h(sa_token))

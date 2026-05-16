"""Tests for new security headers and attendance/config endpoint."""
import os
import uuid
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://pdf-editor-lite.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@payroll.app"
ADMIN_PASSWORD = "admin123"


def _login(email, password):
    cap = requests.get(f"{API}/auth/captcha").json()
    answer = (cap["a"] + cap["b"]) if cap["op"] == "+" else (cap["a"] - cap["b"])
    r = requests.post(f"{API}/auth/login", json={
        "email": email, "password": password,
        "captcha_token": cap["token"], "captcha_answer": answer,
    })
    return r


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


# ---------- SECURITY HEADERS ----------
def test_security_headers_on_health():
    r = requests.get(f"{API}/health")
    assert r.status_code == 200
    h = r.headers
    assert h.get("Strict-Transport-Security") == "max-age=31536000; includeSubDomains"
    assert h.get("X-Content-Type-Options") == "nosniff"
    assert h.get("X-Frame-Options") == "DENY"
    assert h.get("Referrer-Policy") == "no-referrer"
    assert h.get("Permissions-Policy") == "geolocation=(self), camera=(self), microphone=(), payment=()"
    assert h.get("Content-Security-Policy") == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def test_security_headers_on_captcha():
    r = requests.get(f"{API}/auth/captcha")
    assert r.status_code == 200
    assert "Strict-Transport-Security" in r.headers
    assert r.headers.get("X-Frame-Options") == "DENY"


def test_security_headers_on_error_response():
    # 404 should still have headers
    r = requests.get(f"{API}/nonexistent_route_xyz")
    assert r.status_code in (404, 405)
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


# ---------- ATTENDANCE CONFIG ----------
class _Ctx:
    pass


ctx = _Ctx()


def test_setup_tenant_and_employee():
    admin = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert admin.status_code == 200
    ctx.admin = admin.json()["access_token"]

    suffix = uuid.uuid4().hex[:8]
    r = requests.post(f"{API}/admin/employers", headers=_hdr(ctx.admin), json={
        "name": f"TEST_CfgCo_{suffix}",
        "admin_email": f"cfg_{suffix}@testmail.com",
        "admin_password": "EmpPass123!",
        "admin_name": "Cfg Admin",
    })
    assert r.status_code == 200, r.text
    ctx.tenant_id = r.json()["id"]
    ctx.emp_email = f"cfg_{suffix}@testmail.com"
    er = _login(ctx.emp_email, "EmpPass123!")
    ctx.employer_token = er.json()["access_token"]

    # create employee with config 1
    es = uuid.uuid4().hex[:6]
    emp = requests.post(f"{API}/employees", headers=_hdr(ctx.employer_token), json={
        "name": "Cfg Worker", "email": f"w_{es}@testmail.com",
        "password": "WrkPass1!", "emp_code": f"W{es.upper()}",
        "monthly_salary": 40000, "attendance_config_id": 1,
    })
    assert emp.status_code == 200, emp.text
    ctx.emp_id = emp.json()["id"]
    ctx.worker_email = f"w_{es}@testmail.com"
    ctx.worker_pwd = "WrkPass1!"

    wl = _login(ctx.worker_email, ctx.worker_pwd)
    assert wl.status_code == 200
    ctx.worker_token = wl.json()["access_token"]


def test_config_1_tap_only():
    r = requests.get(f"{API}/attendance/config", headers=_hdr(ctx.worker_token))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["config_id"] == 1
    assert d["requires_facial"] is False
    assert d["requires_geo"] is False
    assert d["geo_fence_enforced"] is False
    assert "max_backdate_days" in d


def test_config_5_facial_only_override():
    # PUT employee with config 5 (Facial)
    r = requests.put(f"{API}/employees/{ctx.emp_id}", headers=_hdr(ctx.employer_token), json={
        "attendance_config_id": 5,
    })
    assert r.status_code == 200, r.text
    r2 = requests.get(f"{API}/attendance/config", headers=_hdr(ctx.worker_token))
    d = r2.json()
    assert d["config_id"] == 5
    assert d["requires_facial"] is True
    assert d["requires_geo"] is False
    assert d["geo_fence_enforced"] is False


def test_config_8_facial_plus_geo_with_fence_enabled():
    # First enable tenant geo-fence
    body = {"attendance": {"default_config_id": 1,
                           "geo_fence": {"enabled": True, "center_lat": 12.97, "center_lng": 77.59, "radius_m": 100},
                           "working_days_per_month": 26}}
    r0 = requests.put(f"{API}/tenant/settings", headers=_hdr(ctx.employer_token), json=body)
    assert r0.status_code == 200

    r = requests.put(f"{API}/employees/{ctx.emp_id}", headers=_hdr(ctx.employer_token), json={
        "attendance_config_id": 8,
    })
    assert r.status_code == 200
    r2 = requests.get(f"{API}/attendance/config", headers=_hdr(ctx.worker_token))
    d = r2.json()
    assert d["config_id"] == 8
    assert d["requires_facial"] is True
    assert d["requires_geo"] is True
    assert d["geo_fence_enforced"] is True


def test_config_8_geo_fence_disabled_at_tenant_level():
    # Disable tenant geo-fence; config 8 should still require_facial/geo but enforced=False
    body = {"attendance": {"default_config_id": 1, "geo_fence": {"enabled": False}, "working_days_per_month": 26}}
    requests.put(f"{API}/tenant/settings", headers=_hdr(ctx.employer_token), json=body)
    r = requests.get(f"{API}/attendance/config", headers=_hdr(ctx.worker_token))
    d = r.json()
    assert d["config_id"] == 8
    assert d["requires_geo"] is True
    assert d["geo_fence_enforced"] is False  # tenant override disabled

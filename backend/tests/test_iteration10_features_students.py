"""Iteration 10 — Permission framework + Students module backend tests.

Covers:
  * GET /api/features public catalog (payroll + students)
  * GET /api/me/features for SA / employer / employee
  * PUT /api/admin/employers/{tid}/features (grant + cascade revoke)
  * PUT /api/employees/{user_id}/features (subset rule, 400 on invalid)
  * require_feature('students') gate -> 403 message when missing
  * Students CRUD + search + aadhaar masking
  * File upload (magic-byte 415, multipart success, X-Content-Type-Options, 401 w/o auth)
  * Signed-token download
  * Sheets info + configure error path
  * Regression: NoraTech default enabled_features=['payroll']

After test, restores NoraTech to ['payroll'].
"""
import io
import os
import struct
import uuid
import zlib

import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

SUPER = ("admin@payroll.app", "admin123")
EMPLOYER = ("apoorvchandra01+employer@gmail.com", "demoadmin123")
EMPLOYEE = ("apoorvchandra01@gmail.com", "emp123456")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _captcha():
    cap = requests.get(f"{API}/auth/captcha", timeout=15).json()
    a, b, op = cap["a"], cap["b"], cap["op"]
    ans = a + b if op == "+" else (a - b if op == "-" else a * b)
    return cap["token"], ans


def _login(email, password):
    tok, ans = _captcha()
    r = requests.post(f"{API}/auth/login", json={
        "email": email, "password": password,
        "captcha_token": tok, "captcha_answer": ans,
    }, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _png_bytes():
    """Tiny valid 1x1 PNG (magic header + IHDR + IDAT + IEND)."""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(typ, data):
        return (
            struct.pack(">I", len(data))
            + typ
            + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00\xff\x00\x00"
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


# ---------------------------------------------------------------------------
# Module-scope fixtures: tokens + NoraTech employer_id
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def sa_token():
    return _login(*SUPER)


@pytest.fixture(scope="module")
def noratech_id(sa_token):
    r = requests.get(f"{API}/admin/employers", headers=_h(sa_token), timeout=15)
    assert r.status_code == 200, r.text
    for t in r.json():
        if "nora" in (t.get("name") or "").lower():
            return t["id"]
    pytest.skip("NoraTech employer not found in seed data")


@pytest.fixture(scope="module")
def grant_students_to_noratech(sa_token, noratech_id):
    """Grant students+payroll, yield, then restore to ['payroll']."""
    r = requests.put(
        f"{API}/admin/employers/{noratech_id}/features",
        headers=_h(sa_token), json={"codes": ["payroll", "students"]}, timeout=15,
    )
    assert r.status_code == 200, r.text
    yield
    requests.put(
        f"{API}/admin/employers/{noratech_id}/features",
        headers=_h(sa_token), json={"codes": ["payroll"]}, timeout=15,
    )


@pytest.fixture(scope="module")
def employer_token(grant_students_to_noratech):
    # Re-login AFTER grant so JWT is fresh (although /me/features is dynamic).
    return _login(*EMPLOYER)


@pytest.fixture(scope="module")
def employee_token():
    return _login(*EMPLOYEE)


# ---------------------------------------------------------------------------
# 1. Public catalog
# ---------------------------------------------------------------------------
def test_features_catalog_has_payroll_and_students():
    r = requests.get(f"{API}/features", timeout=15)
    assert r.status_code == 200
    codes = {f["code"] for f in r.json()}
    assert {"payroll", "students"}.issubset(codes), f"got {codes}"


# ---------------------------------------------------------------------------
# 2. /me/features for SA
# ---------------------------------------------------------------------------
def test_super_admin_me_features(sa_token):
    r = requests.get(f"{API}/me/features", headers=_h(sa_token), timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "super_admin"
    codes = {f["code"] for f in body["features"]}
    assert {"payroll", "students"}.issubset(codes)


# ---------------------------------------------------------------------------
# 3. Regression: NoraTech defaults to ['payroll']
# ---------------------------------------------------------------------------
def test_noratech_default_payroll_only(sa_token, noratech_id):
    r = requests.get(f"{API}/admin/employers", headers=_h(sa_token), timeout=15)
    t = next(t for t in r.json() if t["id"] == noratech_id)
    assert "payroll" in (t.get("enabled_features") or [])


# ---------------------------------------------------------------------------
# 4. Grant students cascades: tenant + employer-admin auto-widened
# ---------------------------------------------------------------------------
def test_grant_students_and_employer_sees_both(employer_token):
    r = requests.get(f"{API}/me/features", headers=_h(employer_token), timeout=15)
    assert r.status_code == 200
    codes = {f["code"] for f in r.json()["features"]}
    assert {"payroll", "students"}.issubset(codes), f"employer got {codes}"


# ---------------------------------------------------------------------------
# 5. Employee initially does NOT have students (no cascade auto-grant)
# ---------------------------------------------------------------------------
def test_employee_does_not_get_students_auto(employee_token):
    r = requests.get(f"{API}/me/features", headers=_h(employee_token), timeout=15)
    assert r.status_code == 200
    codes = {f["code"] for f in r.json()["features"]}
    # Should at minimum have payroll. Students should NOT be auto-granted.
    assert "payroll" in codes
    assert "students" not in codes


# ---------------------------------------------------------------------------
# 6. require_feature('students') gate -> 403 for caller without it
# ---------------------------------------------------------------------------
def test_students_gate_403_without_permission(employee_token):
    r = requests.get(f"{API}/students", headers=_h(employee_token), timeout=15)
    assert r.status_code == 403, r.text
    detail = (r.json().get("detail") or "").lower()
    assert "feature" in detail or "permission" in detail or "students" in detail


# ---------------------------------------------------------------------------
# 7. Employer cannot grant feature their tenant doesn't have
# ---------------------------------------------------------------------------
def test_employer_cannot_grant_disabled_feature(sa_token, noratech_id, employer_token, employee_token):
    # First, temporarily revoke students from tenant.
    requests.put(f"{API}/admin/employers/{noratech_id}/features",
                 headers=_h(sa_token), json={"codes": ["payroll"]}, timeout=15)

    # Find employee user_id via the employer's employees listing.
    r = requests.get(f"{API}/employees", headers=_h(employer_token), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    emp_list = body if isinstance(body, list) else (body.get("items") or [])
    if not emp_list:
        pytest.skip("No employees in employer's tenant")
    target_user_id = None
    for e in emp_list:
        if e.get("email") == EMPLOYEE[0]:
            target_user_id = e.get("user_id") or e.get("_id") or e.get("id")
            break
    if not target_user_id:
        target_user_id = emp_list[0].get("user_id") or emp_list[0].get("_id") or emp_list[0].get("id")

    # Now employer tries to grant students -> 400
    r = requests.put(
        f"{API}/employees/{target_user_id}/features",
        headers=_h(employer_token), json={"codes": ["students"]}, timeout=15,
    )
    assert r.status_code == 400, r.text
    assert "students" in r.text.lower() or "enabled" in r.text.lower()

    # Restore: grant students back to tenant.
    requests.put(f"{API}/admin/employers/{noratech_id}/features",
                 headers=_h(sa_token), json={"codes": ["payroll", "students"]}, timeout=15)


# ---------------------------------------------------------------------------
# 8. Employer grants 'students' to employee successfully
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def employee_user_id(employer_token):
    r = requests.get(f"{API}/employees", headers=_h(employer_token), timeout=15)
    body = r.json()
    emp_list = body if isinstance(body, list) else (body.get("items") or [])
    for e in emp_list:
        if e.get("email") == EMPLOYEE[0]:
            return e.get("user_id") or e.get("_id") or e.get("id")
    pytest.skip(f"Employee {EMPLOYEE[0]} not found")


def test_employer_grants_students_to_employee(employer_token, employee_user_id):
    r = requests.put(
        f"{API}/employees/{employee_user_id}/features",
        headers=_h(employer_token), json={"codes": ["payroll", "students"]}, timeout=15,
    )
    assert r.status_code == 200, r.text
    assert set(r.json()["feature_permissions"]) == {"payroll", "students"}

    # Employee /me/features now reflects students
    emp_tok = _login(*EMPLOYEE)
    r2 = requests.get(f"{API}/me/features", headers=_h(emp_tok), timeout=15)
    codes = {f["code"] for f in r2.json()["features"]}
    assert "students" in codes


# ---------------------------------------------------------------------------
# 9. STUDENTS CRUD (employer scope)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def created_student(employer_token):
    payload = {"name": "TEST_Alice", "mobile": "9999900001", "aadhaar": "123412341234"}
    r = requests.post(f"{API}/students", headers=_h(employer_token), json=payload, timeout=15)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["name"] == "TEST_Alice"
    assert s.get("aadhaar_masked") == "XXXX XXXX 1234"
    assert "aadhaar" not in s, "raw aadhaar leaked!"
    assert "id" in s or "_id" in s
    yield s
    sid = s.get("id") or s.get("_id")
    requests.delete(f"{API}/students/{sid}", headers=_h(employer_token), timeout=15)


def test_create_student_returns_masked_aadhaar(created_student):
    assert created_student["aadhaar_masked"] == "XXXX XXXX 1234"
    assert int(created_student.get("serial_no", "0")) >= 1


def test_list_students_finds_alice(employer_token, created_student):
    r = requests.get(f"{API}/students", headers=_h(employer_token), timeout=15)
    assert r.status_code == 200
    body = r.json()
    items = body.get("items") if isinstance(body, dict) else body
    sid = created_student.get("id") or created_student.get("_id")
    assert any((s.get("id") or s.get("_id")) == sid for s in items)


def test_search_students_q(employer_token, created_student):
    r = requests.get(f"{API}/students?q=TEST_Alice", headers=_h(employer_token), timeout=15)
    assert r.status_code == 200
    items = r.json().get("items") or []
    assert any("TEST_Alice" in (s.get("name") or "") for s in items)


def test_get_student(employer_token, created_student):
    sid = created_student.get("id") or created_student.get("_id")
    r = requests.get(f"{API}/students/{sid}", headers=_h(employer_token), timeout=15)
    assert r.status_code == 200
    assert r.json()["name"] == "TEST_Alice"


def test_patch_student(employer_token, created_student):
    sid = created_student.get("id") or created_student.get("_id")
    r = requests.patch(f"{API}/students/{sid}", headers=_h(employer_token),
                       json={"name": "TEST_Alice Updated"}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "TEST_Alice Updated"


# ---------------------------------------------------------------------------
# 10. FILE UPLOAD
# ---------------------------------------------------------------------------
def test_file_upload_magic_byte_rejects_fake_png(employer_token, created_student):
    sid = created_student.get("id") or created_student.get("_id")
    files = {"file": ("fake.png", b"this is not a png", "image/png")}
    r = requests.post(f"{API}/students/{sid}/files/photo",
                      headers=_h(employer_token), files=files, timeout=20)
    assert r.status_code == 415, r.text


def test_file_upload_real_png_succeeds(employer_token, created_student):
    sid = created_student.get("id") or created_student.get("_id")
    png = _png_bytes()
    files = {"file": ("photo.png", png, "image/png")}
    r = requests.post(f"{API}/students/{sid}/files/photo",
                      headers=_h(employer_token), files=files, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("files", {}).get("photo", {}).get("file_id")
    return body


def test_download_requires_auth(employer_token, created_student):
    sid = created_student.get("id") or created_student.get("_id")
    r = requests.get(f"{API}/students/{sid}", headers=_h(employer_token), timeout=15)
    file_id = r.json().get("files", {}).get("photo", {}).get("file_id")
    if not file_id:
        pytest.skip("no photo uploaded")
    # No auth -> 401
    r2 = requests.get(f"{API}/students/files/{file_id}", timeout=15)
    assert r2.status_code == 401, r2.text


def test_download_with_bearer_streams_with_headers(employer_token, created_student):
    sid = created_student.get("id") or created_student.get("_id")
    r = requests.get(f"{API}/students/{sid}", headers=_h(employer_token), timeout=15)
    file_id = r.json().get("files", {}).get("photo", {}).get("file_id")
    if not file_id:
        pytest.skip("no photo uploaded")
    r2 = requests.get(f"{API}/students/files/{file_id}",
                      headers=_h(employer_token), timeout=20)
    assert r2.status_code == 200, r2.text
    assert "attachment" in (r2.headers.get("Content-Disposition") or "").lower()
    assert r2.headers.get("X-Content-Type-Options", "").lower() == "nosniff"
    assert len(r2.content) > 0


def test_delete_file(employer_token, created_student):
    sid = created_student.get("id") or created_student.get("_id")
    r = requests.delete(f"{API}/students/{sid}/files/photo",
                        headers=_h(employer_token), timeout=15)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# 11. SHEETS INFO + configure error path
# ---------------------------------------------------------------------------
def test_sheets_info(employer_token):
    r = requests.get(f"{API}/students/_sheets/info",
                     headers=_h(employer_token), timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("configured") is True
    assert "admission-data@" in (body.get("service_account_email") or "")


def test_sheets_configure_bogus_returns_400_not_500(employer_token):
    r = requests.put(f"{API}/students/_sheets/configure",
                     headers=_h(employer_token),
                     json={"url_or_id": "https://docs.google.com/spreadsheets/d/BOGUS_DOES_NOT_EXIST_XYZ/edit"},
                     timeout=30)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# 12. Soft-delete + 404 on subsequent GET
# ---------------------------------------------------------------------------
def test_delete_student_then_404(employer_token):
    # Create one to delete
    r = requests.post(f"{API}/students", headers=_h(employer_token),
                      json={"name": "TEST_ToDelete", "mobile": "9999900099"}, timeout=15)
    assert r.status_code == 200, r.text
    sid = r.json().get("id") or r.json().get("_id")
    rd = requests.delete(f"{API}/students/{sid}", headers=_h(employer_token), timeout=15)
    assert rd.status_code == 200
    r2 = requests.get(f"{API}/students/{sid}", headers=_h(employer_token), timeout=15)
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# 13. Reset: revoke students from employee at end
# ---------------------------------------------------------------------------
def test_zz_cleanup_revoke_employee_students(employer_token, employee_user_id):
    requests.put(f"{API}/employees/{employee_user_id}/features",
                 headers=_h(employer_token), json={"codes": ["payroll"]}, timeout=15)

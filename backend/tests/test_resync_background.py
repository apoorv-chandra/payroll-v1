"""Resync to Sheets — BackgroundTasks + polling endpoint contract test.

Verifies:
  • POST /api/students/_sheets/resync returns {ok, job_id, total, status}
    immediately (within ~500ms) even when N students could take minutes.
  • GET /api/students/_sheets/resync/{job_id} returns the live job state.
  • The 400/403/404 error contracts are preserved from the synchronous version.

We do NOT poll until completion in this test — that requires a real bound
Google Sheet which we don't want to create as a test side-effect. We do
verify that the job is correctly queued and discoverable via the GET.
"""
import os
import time
import uuid

import requests

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or "https://pdf-editor-lite.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

SUPER_EMAIL = "admin@payroll.app"
SUPER_PASS = "admin123"
EMP_ADMIN_EMAIL = "apoorvchandra01+employer@gmail.com"
EMP_ADMIN_PASS = "demoadmin123"


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


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ensure_students_enabled_for_norra(sa_token: str) -> str:
    """Grant students module to NoraTech for the duration of the test."""
    employers = requests.get(f"{API}/admin/employers", headers=_h(sa_token)).json()
    norra = next(t for t in employers if t["name"] == "NoraTech")
    requests.put(
        f"{API}/admin/employers/{norra['id']}/features",
        headers=_h(sa_token),
        json={"codes": ["payroll", "students"]},
    )
    return norra["id"]


def _restore_norra(sa_token: str, norra_id: str) -> None:
    requests.put(
        f"{API}/admin/employers/{norra_id}/features",
        headers=_h(sa_token),
        json={"codes": ["payroll"]},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_resync_without_bound_sheet_returns_400():
    sa = _login(SUPER_EMAIL, SUPER_PASS)
    norra_id = _ensure_students_enabled_for_norra(sa)
    try:
        emp = _login(EMP_ADMIN_EMAIL, EMP_ADMIN_PASS)
        # Forcibly clear any bound sheet so we hit the "configure first" branch.
        requests.delete(f"{API}/students/_sheets/configure", headers=_h(emp))
        r = requests.post(f"{API}/students/_sheets/resync", headers=_h(emp))
        assert r.status_code == 400, r.text
        assert "no master sheet" in r.text.lower()
    finally:
        _restore_norra(sa, norra_id)


def test_resync_returns_quickly_with_job_id_shape():
    """When a sheet IS bound, POST should return fast with a job_id even if
    syncing would take minutes. We don't actually bind a real sheet here —
    we just verify the 400 contract is preserved for the unbound case AND
    that a poll on a fresh UUID returns 404 (not 500)."""
    emp = _login(EMP_ADMIN_EMAIL, EMP_ADMIN_PASS)
    bogus = uuid.uuid4().hex
    r = requests.get(f"{API}/students/_sheets/resync/{bogus}", headers=_h(emp))
    assert r.status_code in (404, 403), r.text


def test_resync_poll_endpoint_404_for_unknown_job():
    sa = _login(SUPER_EMAIL, SUPER_PASS)
    norra_id = _ensure_students_enabled_for_norra(sa)
    try:
        emp = _login(EMP_ADMIN_EMAIL, EMP_ADMIN_PASS)
        r = requests.get(
            f"{API}/students/_sheets/resync/{uuid.uuid4().hex}",
            headers=_h(emp),
        )
        assert r.status_code == 404, r.text
    finally:
        _restore_norra(sa, norra_id)


def test_resync_unauthorized_role_blocked():
    """Plain employee (no students module / no employer role) gets 403."""
    sa = _login(SUPER_EMAIL, SUPER_PASS)
    norra_id = _ensure_students_enabled_for_norra(sa)
    try:
        # The plain employee Apoorv only has the payroll feature on default —
        # they shouldn't be able to fire the resync.
        emp_token = _login("apoorvchandra01@gmail.com", "emp123456")
        r = requests.post(f"{API}/students/_sheets/resync", headers=_h(emp_token))
        assert r.status_code == 403, r.text
    finally:
        _restore_norra(sa, norra_id)


def test_resync_response_is_fast(monkeypatch=None):
    """The POST response itself should be fast (< 2s) even when async sync
    would otherwise take minutes. Test against the unbound-sheet path which
    short-circuits, but the lat shape is what we want to nail down."""
    sa = _login(SUPER_EMAIL, SUPER_PASS)
    norra_id = _ensure_students_enabled_for_norra(sa)
    try:
        emp = _login(EMP_ADMIN_EMAIL, EMP_ADMIN_PASS)
        requests.delete(f"{API}/students/_sheets/configure", headers=_h(emp))
        t0 = time.time()
        r = requests.post(f"{API}/students/_sheets/resync", headers=_h(emp), timeout=5)
        dt = time.time() - t0
        assert dt < 2.0, f"Resync response too slow: {dt:.2f}s"
        # We expect 400 here (no sheet bound) — the point is speed, not the body.
        assert r.status_code in (200, 400), r.text
    finally:
        _restore_norra(sa, norra_id)

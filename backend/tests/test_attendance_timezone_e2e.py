"""BUG-1 TIMEZONE regression: end-to-end attendance datetime serialization.

Verifies:
  • POST /api/attendance/mark response.at contains tz suffix
  • GET  /api/attendance/today returns record.check_in_at with `Z` or `+00:00`
  • GET  /api/attendance/today.date equals current IST date
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
EMAIL = "apoorvchandra01@gmail.com"
PASSWORD = "emp123456"

IST = timezone(timedelta(hours=5, minutes=30))
TZ_SUFFIX_RE = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")


def _solve_captcha(c: dict) -> int:
    a, b, op = c["a"], c["b"], c["op"]
    return {"+": a + b, "-": a - b, "*": a * b, "x": a * b, "×": a * b}[op]


@pytest.fixture(scope="module")
def employee_token():
    s = requests.Session()
    cap = s.get(f"{BASE_URL}/api/auth/captcha", timeout=15).json()
    ans = _solve_captcha(cap)
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": EMAIL,
            "password": PASSWORD,
            "captcha_token": cap["token"],
            "captcha_answer": ans,
        },
        timeout=15,
    )
    assert r.status_code == 200, f"Employee login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(employee_token):
    return {"Authorization": f"Bearer {employee_token}"}


def test_grant_consents(auth_headers):
    """Ensure the employee has geo_location + data_processing consent so the
    subsequent attendance mark accepts coordinates."""
    r = requests.put(
        f"{BASE_URL}/api/me/privacy/consents",
        headers=auth_headers,
        json={"consents": {"geo_location": True, "data_processing": True, "face_capture": False}},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    consents = body.get("consents") or body
    assert consents.get("geo_location") is True
    assert consents.get("data_processing") is True


def test_attendance_mark_returns_tz_aware_iso(auth_headers):
    r = requests.post(
        f"{BASE_URL}/api/attendance/mark",
        headers=auth_headers,
        json={
            "method": "normal",
            "type": "check_in",
            "latitude": 12.97,
            "longitude": 77.59,
            "overwrite": True,
        },
        timeout=15,
    )
    assert r.status_code == 200, f"mark failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["ok"] is True
    assert data["type"] == "check_in"
    at = data["at"]
    assert isinstance(at, str) and at
    assert TZ_SUFFIX_RE.search(at), f"mark.at missing tz suffix: {at!r}"

    # date returned matches today in IST
    expected_today = datetime.now(IST).date().isoformat()
    assert data["date"] == expected_today


def test_attendance_today_returns_tz_aware_check_in(auth_headers):
    r = requests.get(f"{BASE_URL}/api/attendance/today", headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["marked"] is True, f"expected marked=True after previous test, got {body}"
    rec = body["record"]
    ci = rec["check_in_at"]
    assert isinstance(ci, str), f"check_in_at not string: {ci!r}"
    assert TZ_SUFFIX_RE.search(ci), f"check_in_at missing tz suffix: {ci!r}"

    # The date in the response must equal today in IST (not the UTC day).
    expected_today_ist = datetime.now(IST).date().isoformat()
    assert body["date"] == expected_today_ist, (
        f"Expected today's IST date {expected_today_ist}, got {body['date']}"
    )


def test_check_in_at_parses_and_is_recent(auth_headers):
    r = requests.get(f"{BASE_URL}/api/attendance/today", headers=auth_headers, timeout=15)
    body = r.json()
    ci = body["record"]["check_in_at"]
    # Python 3.11+ fromisoformat tolerates trailing 'Z'? No — normalise.
    norm = ci.replace("Z", "+00:00")
    dt = datetime.fromisoformat(norm)
    assert dt.tzinfo is not None
    delta = abs((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
    assert delta < 600, f"check_in_at not within 10 minutes of now: {ci} (delta={delta}s)"

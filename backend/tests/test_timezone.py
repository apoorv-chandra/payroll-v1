"""Regression tests for timezone handling.

We had a bug where:
  • `today_iso()` used the server's local date (UTC on Render), so a 1 AM IST
    check-in could land on the previous calendar day.
  • Motor clients defaulted to tz-NAIVE datetimes, so FastAPI serialized them
    without a "Z"/"+00:00" suffix, causing browsers to interpret them as
    LOCAL time and display the wrong hour.

These tests pin down both contracts.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.utils import app_tz, today_iso


def test_today_iso_uses_business_timezone():
    """today_iso() must reflect the date in Asia/Kolkata, not UTC."""
    expected = datetime.now(app_tz()).date().isoformat()
    assert today_iso() == expected


def test_app_tz_is_ist():
    tz = app_tz()
    # IST is UTC+05:30; sanity-check the offset at "now".
    offset = datetime.now(tz).utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 5.5 * 3600


def test_motor_client_is_tz_aware():
    """When we read datetimes back from Mongo they should carry tzinfo so
    FastAPI emits '+00:00' (or 'Z') in JSON. Without tz_aware=True the
    datetime is naive and the suffix is dropped, breaking browsers."""
    from app.db import get_client

    client = get_client()
    # pymongo exposes the codec_options used by every collection.
    opts = client.codec_options
    assert opts.tz_aware is True
    # And the default tz is UTC (BSON datetimes are UTC).
    assert opts.tzinfo in (None, timezone.utc)

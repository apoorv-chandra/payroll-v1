"""Email service (Resend). Only the welcome email is enabled in this version.

All other notifications go via WhatsApp; keep helpers around so they can
be re-enabled later by setting the ``feature_email_<event>`` flag.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, List

import resend

from ..config import settings

logger = logging.getLogger(__name__)

if settings.RESEND_API_KEY:
    resend.api_key = settings.RESEND_API_KEY


EMAIL_LAYOUT = """
<!doctype html><html><body style="margin:0;background:#F9FAFB;font-family:'Helvetica Neue',Arial,sans-serif;color:#0A0A0A;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F9FAFB;padding:24px 0;">
  <tr><td align="center">
    <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;">
      <tr><td style="padding:20px 24px;border-bottom:1px solid #F3F4F6;">
        <table role="presentation" width="100%"><tr>
          <td style="font-weight:700;font-size:18px;letter-spacing:-0.01em;">Payroll</td>
          <td align="right" style="font-size:11px;color:#737373;text-transform:uppercase;letter-spacing:0.12em;">{tag}</td>
        </tr></table>
      </td></tr>
      <tr><td style="padding:24px;">{body}</td></tr>
      <tr><td style="padding:16px 24px;border-top:1px solid #F3F4F6;font-size:11px;color:#9CA3AF;">
        Sent by Payroll & Attendance. If this wasn't you, ignore this email.
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>
"""


def render_email(tag: str, body_html: str) -> str:
    return EMAIL_LAYOUT.format(tag=tag, body=body_html)


def login_url() -> str:
    return f"{settings.APP_BASE_URL}/login" if settings.APP_BASE_URL else "/login"


async def send_email(
    to: str,
    subject: str,
    html: str,
    attachments: Optional[List[dict]] = None,
) -> Optional[str]:
    """Send an email through Resend. Failures are swallowed and logged."""
    if not settings.RESEND_API_KEY:
        logger.info("[email-mock] to=%s subject=%s", to, subject)
        return None
    params = {
        "from": settings.SENDER_EMAIL,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if attachments:
        params["attachments"] = attachments
    try:
        res = await asyncio.to_thread(resend.Emails.send, params)
        eid = (res or {}).get("id") if isinstance(res, dict) else getattr(res, "id", None)
        logger.info("[email-sent] to=%s id=%s", to, eid)
        return eid
    except Exception as e:
        logger.error("[email-fail] to=%s subject=%s err=%s", to, subject, e)
        return None


def render_welcome_body(employee_name: str, company: str, email: str, password: str, emp_code: str) -> str:
    return f"""
      <h2 style="margin:0 0 12px 0;font-size:20px;letter-spacing:-0.01em;">Welcome to {company} 👋</h2>
      <p style="margin:0 0 16px 0;color:#4B5563;line-height:1.55;">
        Your account has been created. You can mark attendance, apply for leave and download salary slips from your phone.
      </p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px;width:100%;font-size:14px;">
        <tr><td style="padding:10px 14px;color:#737373;">Login email</td><td style="padding:10px 14px;font-weight:600;">{email}</td></tr>
        <tr><td style="padding:10px 14px;color:#737373;border-top:1px solid #F3F4F6;">Password</td><td style="padding:10px 14px;font-family:monospace;border-top:1px solid #F3F4F6;">{password}</td></tr>
        <tr><td style="padding:10px 14px;color:#737373;border-top:1px solid #F3F4F6;">Code</td><td style="padding:10px 14px;border-top:1px solid #F3F4F6;">{emp_code}</td></tr>
      </table>
      <p style="margin:18px 0 8px 0;">
        <a href="{login_url()}" style="display:inline-block;background:#0A0A0A;color:#FFFFFF;text-decoration:none;padding:12px 18px;border-radius:8px;font-weight:600;">Sign in to Payroll</a>
      </p>
      <p style="margin:8px 0 0 0;font-size:12px;color:#9CA3AF;">Please change your password after first login.</p>
    """

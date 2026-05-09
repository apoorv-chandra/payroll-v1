"""Application configuration loaded from environment variables.

All settings are loaded once at import time. Never read os.environ from
application code — always go through this module so every value has a
single, documented source of truth.
"""
from __future__ import annotations

import os
import logging
from functools import lru_cache

from dotenv import load_dotenv

# Load .env early so subsequent os.environ reads see the values.
load_dotenv()


class Settings:
    # --- Database --------------------------------------------------------
    MONGO_URL: str = os.environ["MONGO_URL"]
    DB_NAME: str = os.environ["DB_NAME"]

    # --- Auth ------------------------------------------------------------
    JWT_SECRET: str = os.environ["JWT_SECRET"]
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_HOURS: int = int(os.environ.get("JWT_EXPIRES_HOURS", "12"))

    ADMIN_EMAIL: str = os.environ.get("ADMIN_EMAIL", "admin@payroll.app").lower()
    ADMIN_PASSWORD: str = os.environ.get("ADMIN_PASSWORD", "admin123")

    # --- App -------------------------------------------------------------
    APP_BASE_URL: str = os.environ.get("APP_BASE_URL", "")
    CORS_ORIGINS: list[str] = [
        o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()
    ] or ["*"]

    # --- Email (Resend) --------------------------------------------------
    RESEND_API_KEY: str = os.environ.get("RESEND_API_KEY", "")
    SENDER_EMAIL: str = os.environ.get("SENDER_EMAIL", "Payroll <onboarding@resend.dev>")

    # --- WhatsApp (Twilio) ----------------------------------------------
    TWILIO_ACCOUNT_SID: str = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_FROM: str = os.environ.get(
        "TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"
    )

    # --- Logging ---------------------------------------------------------
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def configure_logging() -> None:
    logging.basicConfig(
        level=get_settings().LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )


settings = get_settings()

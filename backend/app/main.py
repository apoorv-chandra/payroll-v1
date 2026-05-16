"""FastAPI application factory."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .config import configure_logging, settings
from .db import ensure_indexes
from .scheduler import start_scheduler, stop_scheduler
from .services.seed import seed_super_admin, seed_platform_settings, backfill_signup_codes
from .services.migrate import migrate_per_tenant_collections
from .utils import now_utc

from .routes import auth as auth_routes
from .routes import admin as admin_routes
from .routes import employees as employees_routes
from .routes import attendance as attendance_routes
from .routes import leaves as leaves_routes
from .routes import payroll as payroll_routes
from .routes import privacy as privacy_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    await ensure_indexes()
    await seed_super_admin()
    await seed_platform_settings()
    await backfill_signup_codes()
    await migrate_per_tenant_collections()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds defence-in-depth headers on every API response.

    These complement HTTPS+TLS (which already encrypts traffic in transit)
    and harden the client against XSS, MIME-sniffing and referer leakage.
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        # HSTS — force HTTPS for 1 year (only meaningful when served behind
        # TLS on Render / Cloudflare; benign in dev).
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        # MIME-sniffing protection.
        h.setdefault("X-Content-Type-Options", "nosniff")
        # Clickjacking protection — we don't embed in iframes anywhere.
        h.setdefault("X-Frame-Options", "DENY")
        # Limit Referer leakage to third parties.
        h.setdefault("Referrer-Policy", "no-referrer")
        # Block legacy power-features unless the page explicitly opts in.
        h.setdefault(
            "Permissions-Policy",
            "geolocation=(self), camera=(self), microphone=(), payment=()",
        )
        # CSP — the API itself never serves HTML so we lock everything down.
        # The React SPA is served by Cloudflare Pages, which sets its own CSP.
        h.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        return response


def create_app() -> FastAPI:
    app = FastAPI(title="Payroll & Attendance API", lifespan=lifespan, version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)

    api = APIRouter(prefix="/api")
    api.include_router(auth_routes.router)
    api.include_router(admin_routes.router)
    api.include_router(employees_routes.router)
    api.include_router(attendance_routes.router)
    api.include_router(leaves_routes.router)
    api.include_router(payroll_routes.router)
    api.include_router(privacy_routes.router)

    @api.get("/health")
    async def health():
        return {"ok": True, "ts": now_utc().isoformat()}

    app.include_router(api)
    return app


app = create_app()

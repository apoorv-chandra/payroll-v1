"""FastAPI application factory."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import configure_logging, settings
from .db import ensure_indexes
from .scheduler import start_scheduler, stop_scheduler
from .services.seed import seed_super_admin, seed_platform_settings
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
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(title="Payroll & Attendance API", lifespan=lifespan, version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

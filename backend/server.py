"""Compatibility shim — supervisor still launches `uvicorn server:app`.

The application is implemented in :mod:`app.main`; this module merely
re-exports the FastAPI instance so existing process supervisors and
deployment scripts keep working unchanged.
"""
from app.main import app  # noqa: F401

__all__ = ["app"]

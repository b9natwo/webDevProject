"""
dashboard/src/main.py
FastAPI application entry point for the Prefix Hub web dashboard.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from dashboard.src.auth.session import SessionMiddleware
from dashboard.src.routers import analytics, artists, auth, feeds, guilds, health, premium
from shared.config import get_settings
from shared.logging_config import configure_logging

settings = get_settings()
configure_logging(level=settings.log_level, service_name="prefix-hub-dashboard")
log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Prefix Hub Dashboard",
        description="Management dashboard for Prefix Hub Discord bot",
        version="2.0.0",
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
    )

    # ── Middleware ─────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SessionMiddleware, secret_key=settings.dashboard_secret_key.get_secret_value())

    # ── Routers ────────────────────────────────────────────────────────
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/auth")
    app.include_router(guilds.router, prefix="/api/guilds")
    app.include_router(artists.router, prefix="/api/guilds")
    app.include_router(feeds.router, prefix="/api/feeds")
    app.include_router(premium.router, prefix="/api/premium")
    app.include_router(analytics.router, prefix="/api/analytics")

    # ── Static frontend ────────────────────────────────────────────────
    import os
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    # ── Global error handler ───────────────────────────────────────────
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "dashboard.src.main:app",
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        reload=not settings.is_production,
    )

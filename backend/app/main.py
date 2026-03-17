"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.data_quality import router as quality_router
from app.api.decisions import router as decisions_router
from app.api.reconcile import router as reconcile_router
from app.config import get_settings
from app.middleware.rate_limit import RateLimitMiddleware

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Log startup and shutdown events."""
    settings = get_settings()
    logger.info("Starting %s v%s (debug=%s)", settings.app_title, settings.app_version, settings.debug)
    yield
    logger.info("Shutting down %s", settings.app_title)


def create_app() -> FastAPI:
    """Application factory — returns a configured FastAPI instance."""
    s = get_settings()

    # Disable interactive docs in production to reduce attack surface
    docs_url = "/docs" if s.debug else None
    redoc_url = "/redoc" if s.debug else None

    app = FastAPI(
        title=s.app_title,
        version=s.app_version,
        description=(
            "Clinical Data Reconciliation Engine — AI-assisted decision support prototype. "
            "NOT a medical device."
        ),
        docs_url=docs_url,
        redoc_url=redoc_url,
        lifespan=lifespan,
    )

    # Rate limiting — must be added before CORS so 429s include CORS headers
    app.add_middleware(RateLimitMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=False,                        # no cookies used
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "x-api-key"],   # explicit, not wildcard
    )

    app.include_router(reconcile_router, prefix=s.api_prefix)
    app.include_router(quality_router, prefix=s.api_prefix)
    app.include_router(decisions_router, prefix=s.api_prefix)

    @app.get("/health", tags=["system"], include_in_schema=False)
    async def health_check() -> JSONResponse:
        """Simple liveness probe."""
        return JSONResponse({"status": "ok", "version": s.app_version})

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next) -> JSONResponse:
        """Attach baseline security headers to every response."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


app = create_app()

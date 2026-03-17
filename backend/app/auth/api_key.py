"""API key middleware — rejects requests missing a valid x-api-key header."""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import get_settings

_api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


async def require_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    """
    FastAPI dependency that enforces API key authentication.

    Uses constant-time comparison to prevent timing attacks.
    Raises HTTP 401 if key is absent or invalid.
    """
    settings = get_settings()
    if api_key is None or not secrets.compare_digest(api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key

"""Opt-in API-key protection for data-bearing endpoints."""

import secrets

from fastapi import Header, HTTPException

from config import settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require API_KEY when configured; local development remains frictionless."""
    if settings.api_key and (
        not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key)
    ):
        raise HTTPException(status_code=401, detail="API key required")

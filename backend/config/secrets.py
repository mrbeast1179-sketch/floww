"""
backend/config/secrets.py

Azure Key Vault secret retrieval with strict production enforcement.
In production (Azure App Service), ALL secrets MUST come from Key Vault.
Local .env is only used for development — never in production.

Usage:
    from config.secrets import get_secret, require_secret

    mongo_url = require_secret("MONGO_URL")
    api_key = get_secret("API_SECRET_KEY", default="dev-only-key")
"""

from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from typing import Optional

logger = logging.getLogger("config.secrets")

# ── Environment Detection ────────────────────────────────────────────────────

_ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev").lower()
if _ENVIRONMENT in {"production", "staging"} and not is_azure():
    _api_secret = os.environ.get("API_SECRET_KEY")
    if not _api_secret:
        sys.exit(
            "FATAL: API_SECRET_KEY env var is required when ENVIRONMENT="
            f"{_ENVIRONMENT!r}. Refusing to start with default dev key. "
            "Set API_SECRET_KEY in your environment or Azure Key Vault."
        )


# ── Azure Key Vault Client ───────────────────────────────────────────────────

_resolver = SecretResolver()


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Get a secret by name. Returns default if not found."""
    return _resolver.get(name, default)


def require_secret(name: str) -> str:
    """Get a required secret. Raises RuntimeError if missing."""
    return _resolver.require(name)


# ── Convenience: Pre-resolved common secrets ─────────────────────────────────

@lru_cache(maxsize=1)
def get_mongo_url() -> str:
    val = require_secret("MONGO_URL")
    if val is None:
        raise RuntimeError("MONGO_URL is required but not found")
    return val


@lru_cache(maxsize=1)
def get_db_name() -> str:
    return get_secret("DB_NAME", "confluence_decoder") or "confluence_decoder"


@lru_cache(maxsize=1)
def get_api_secret_key() -> str:
    val = require_secret("API_SECRET_KEY")
    if val is None:
        raise RuntimeError("API_SECRET_KEY is required but not found")
    return val


@lru_cache(maxsize=1)
def get_ws_api_token() -> str:
    val = require_secret("WS_API_TOKEN")
    if val is None:
        raise RuntimeError("WS_API_TOKEN is required but not found")
    return val


@lru_cache(maxsize=1)
def get_dash_session_token() -> str:
    val = require_secret("DASH_SESSION_TOKEN")
    if val is None:
        raise RuntimeError("DASH_SESSION_TOKEN is required but not found")
    return val


@lru_cache(maxsize=1)
def get_databento_api_key() -> str:
    return get_secret("DATABENTO_API_KEY", "") or ""


@lru_cache(maxsize=1)
def get_polygon_api_key() -> str:
    return get_secret("POLYGON_API_KEY", "") or ""


@lru_cache(maxsize=1)
def get_alpha_vantage_key() -> str:
    return get_secret("ALPHA_VANTAGE_KEY", "") or ""

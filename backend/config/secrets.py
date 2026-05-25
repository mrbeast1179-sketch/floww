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
from functools import lru_cache
from typing import Optional

logger = logging.getLogger("config.secrets")

# ── Environment Detection ────────────────────────────────────────────────────

def is_production() -> bool:
    """Check if running in production (Azure App Service)."""
    return os.environ.get("ENVIRONMENT", "").lower() == "production"


def is_azure() -> bool:
    """Check if running on Azure App Service."""
    return os.environ.get("WEBSITE_SITE_NAME", "") != ""


# ── Azure Key Vault Client ───────────────────────────────────────────────────

class AzureKeyVaultClient:
    """Retrieve secrets from Azure Key Vault using Managed Identity."""

    def __init__(self, vault_url: Optional[str] = None):
        self._vault_url = vault_url or os.environ.get("AZURE_KEY_VAULT_URI", "")
        self._client = None

    def _get_client(self):
        """Lazy-init the Key Vault client."""
        if self._client is not None:
            return self._client

        if not self._vault_url:
            return None

        try:
            from azure.identity import DefaultAzureCredential  # type: ignore
            from azure.keyvault.secrets import SecretClient  # type: ignore

            credential = DefaultAzureCredential()
            self._client = SecretClient(
                vault_url=self._vault_url,
                credential=credential,
            )
            logger.info(f"Key Vault client initialized: {self._vault_url}")
            return self._client
        except ImportError:
            logger.error("azure-identity or azure-keyvault-secrets not installed")
            return None
        except Exception as e:
            logger.error(f"Key Vault client init failed: {e}")
            return None

    def get_secret(self, name: str) -> Optional[str]:
        """Get a secret from Key Vault. Returns None if not found."""
        client = self._get_client()
        if not client:
            return None

        try:
            # Key Vault secret names use hyphens, env vars use underscores
            kv_name = name.replace("_", "-").lower()
            secret = client.get_secret(kv_name)
            return secret.value
        except Exception as e:
            logger.debug(f"Key Vault secret '{name}' not found: {e}")
            return None


class LocalEnvClient:
    """Fallback: read secrets from environment / .env file.

    WARNING: Only used in development. In production, this client is
    disabled and require_secret() will raise RuntimeError if the
    secret is not in Key Vault.
    """

    def get_secret(self, name: str) -> Optional[str]:
        return os.environ.get(name)


# ── Unified Secret Resolver ──────────────────────────────────────────────────

class SecretResolver:
    """
    Resolves secrets in priority order:
    1. Azure Key Vault (production — REQUIRED)
    2. Environment variables (development only)
    3. Default value (if provided)

    In production, if a required secret is not in Key Vault,
    RuntimeError is raised immediately — no .env fallback.
    """

    def __init__(self):
        self._kv = AzureKeyVaultClient() if is_azure() else None
        self._local = LocalEnvClient()

    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Get a secret value. Returns default if not found anywhere."""
        # 1. Try Key Vault in Azure (production)
        if self._kv:
            value = self._kv.get_secret(name)
            if value is not None:
                return value
            # In production, do NOT fall back to env vars
            if is_production():
                logger.error(f"Secret '{name}' not found in Key Vault (production mode)")
                return default
            # In development, log a warning but continue
            logger.warning(f"Secret '{name}' not in Key Vault, falling back to env")

        # 2. Try environment (development only)
        value = self._local.get_secret(name)
        if value is not None:
            return value

        # 3. Default
        return default

    def require(self, name: str) -> str:
        """Get a required secret. Raises RuntimeError if not found."""
        value = self.get(name)
        if value is None:
            raise RuntimeError(
                f"Required secret '{name}' not found. "
                f"{'Set it in Azure Key Vault.' if is_azure() else 'Set it as environment variable or in .env file.'}"
            )
        return value


# ── Module-level API ─────────────────────────────────────────────────────────

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

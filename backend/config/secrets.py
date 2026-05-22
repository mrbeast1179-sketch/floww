"""
backend/config/secrets.py

Azure Key Vault secret retrieval with local fallback.
All secrets are stored in Azure Key Vault and accessed via Managed Identity.
Local .env is only used as a fallback for development — never in production.

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
            logger.warning("azure-identity or azure-keyvault-secrets not installed")
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
    """Fallback: read secrets from environment / .env file."""

    def get_secret(self, name: str) -> Optional[str]:
        return os.environ.get(name)


# ── Unified Secret Resolver ──────────────────────────────────────────────────

class SecretResolver:
    """
    Resolves secrets in priority order:
    1. Azure Key Vault (production)
    2. Environment variables (always checked)
    3. Default value (if provided)
    """

    def __init__(self):
        self._kv = AzureKeyVaultClient() if is_azure() else None
        self._local = LocalEnvClient()

    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Get a secret value. Returns default if not found anywhere."""
        # 1. Try Key Vault in Azure
        if self._kv:
            value = self._kv.get_secret(name)
            if value is not None:
                return value

        # 2. Try environment
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
                f"Set it in Azure Key Vault or as environment variable."
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
def get_schwab_client_id() -> str:
    return get_secret("SCHWAB_CLIENT_ID", "") or ""


@lru_cache(maxsize=1)
def get_schwab_client_secret() -> str:
    return get_secret("SCHWAB_CLIENT_SECRET", "") or ""


@lru_cache(maxsize=1)
def get_databento_api_key() -> str:
    return get_secret("DATABENTO_API_KEY", "") or ""

"""
Tests for LLM service (OpenRouter) and turboQuantDC cache service.
"""
from __future__ import annotations

import importlib
import os
import sys
import types

import pytest

# ---------------------------------------------------------------------------
# LLM Service Tests
# ---------------------------------------------------------------------------

class TestLLMService:
    """Tests for the LLM service with OpenRouter provider."""

    def _make_service(self, provider="openrouter", openrouter_key="sk-or-v1-test", gemini_key=""):
        """Create a fresh LLMService with controlled env."""
        from services.llm import LLMService
        svc = LLMService.__new__(LLMService)
        svc.provider = provider
        svc.openrouter_key = openrouter_key
        svc.gemini_key = gemini_key
        svc.llm_key = ""
        svc.openrouter_model = "openrouter/free"
        return svc

    def test_is_configured_openrouter(self):
        svc = self._make_service("openrouter", openrouter_key="sk-or-v1-test")
        assert svc.is_configured is True

    def test_is_configured_openrouter_no_key(self):
        svc = self._make_service("openrouter", openrouter_key="")
        assert svc.is_configured is False

    def test_is_configured_gemini(self):
        svc = self._make_service("gemini", gemini_key="test-key")
        assert svc.is_configured is True

    def test_available_providers(self):
        svc = self._make_service("openrouter", openrouter_key="sk-or-v1-test")
        providers = svc.available_providers
        assert len(providers) == 3
        names = [p["name"] for p in providers]
        assert "openrouter" in names
        assert "gemini" in names
        assert "cerebras" in names
        # OpenRouter should be marked as free
        or_prov = next(p for p in providers if p["name"] == "openrouter")
        assert or_prov["free"] is True

    def test_generate_no_key_raises(self):
        svc = self._make_service("openrouter", openrouter_key="")
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY not set"):
            svc.generate("test prompt")

    def test_generate_openrouter_calls_api(self, monkeypatch):
        """Test that generate() calls the OpenRouter API correctly."""
        svc = self._make_service("openrouter", openrouter_key="sk-or-v1-test")

        # Mock the openai client
        mock_choice = types.SimpleNamespace(message=types.SimpleNamespace(content="Test response"))
        mock_usage = types.SimpleNamespace(total_tokens=42)
        mock_completion = types.SimpleNamespace(choices=[mock_choice], usage=mock_usage)

        class MockCompletions:
            def create(self, **kwargs):
                return mock_completion

        class MockChat:
            completions = MockCompletions()

        class MockClient:
            def __init__(self, **kwargs):
                self.chat = MockChat()

        # Patch OpenAI import
        mock_openai = types.ModuleType("openai")
        mock_openai.OpenAI = MockClient
        monkeypatch.setitem(sys.modules, "openai", mock_openai)

        # Also set the env var so _call_openrouter doesn't raise
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")

        result = svc.generate("What is SPX?", system_prompt="You are a trader.", max_tokens=100)

        assert result["text"] == "Test response"
        assert result["provider"] == "openrouter"
        assert result["tokens_used"] == 42

    def test_generate_no_provider_raises(self):
        """When no provider has a key, generate() raises ValueError."""
        svc = self._make_service("unknown_provider", openrouter_key="", gemini_key="")
        with pytest.raises(ValueError, match="No LLM provider configured"):
            svc.generate("test")

    def test_generate_fallback_to_gemini(self, monkeypatch):
        """Test that generate raises ValueError when no provider has a key."""
        svc = self._make_service("openrouter", openrouter_key="", gemini_key="")
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY not set"):
            svc.generate("test")


class TestAnalyzeTradeWithLLM:
    """Tests for the analyze_trade_with_llm function."""

    def test_analyze_trade_calls_generate(self, monkeypatch):
        from services.llm import LLMService

        calls = []

        def mock_generate(self_inner, prompt, system_prompt="", max_tokens=512):
            calls.append({"prompt": prompt, "system_prompt": system_prompt})
            return {"text": "Bullish analysis", "provider": "test", "tokens_used": 10}

        monkeypatch.setattr(LLMService, "generate", mock_generate)

        # Reset singleton
        from services.llm import reset_llm_service
        reset_llm_service()

        import asyncio

        from services.llm import analyze_trade_with_llm

        result = asyncio.run(
            analyze_trade_with_llm("SPX", 5500.0, "BULL", 1_000_000, "UP", 0.75)
        )

        assert result["text"] == "Bullish analysis"
        assert len(calls) == 1
        assert "SPX" in calls[0]["prompt"]
        assert "5500" in calls[0]["prompt"]


# ---------------------------------------------------------------------------
# turboQuantDC Cache Service Tests
# ---------------------------------------------------------------------------

class TestTurboQuantService:
    """Tests for the turboQuantDC cache service."""

    def test_status_without_turboquant(self, monkeypatch):
        """Service should degrade gracefully when turboquantdc is not installed."""
        # Patch HAS_TURBOQUANT to False
        import services.turboquant_cache as tq_mod
        monkeypatch.setattr(tq_mod, "HAS_TURBOQUANT", False)

        from services.turboquant_cache import TurboQuantService, reset_turboquant_service
        reset_turboquant_service()

        svc = TurboQuantService.__new__(TurboQuantService)
        svc._available = False
        svc._default_preset = "balanced"
        svc._default_bits = 4
        svc._fp16_window = 64

        status = svc.status()
        assert status["available"] is False
        assert status["default_preset"] == "balanced"
        assert "presets" in status

    def test_presets(self):
        from services.turboquant_cache import PRESETS
        assert "lossless" in PRESETS
        assert "balanced" in PRESETS
        assert "aggressive" in PRESETS
        assert "compression" in PRESETS["balanced"]

    def test_create_cache_raises_when_unavailable(self):
        from services.turboquant_cache import TurboQuantService

        svc = TurboQuantService.__new__(TurboQuantService)
        svc._available = False

        with pytest.raises(ImportError, match="turboquantdc not installed"):
            svc.create_cache()

    def test_get_compression_stats_unavailable(self):
        from services.turboquant_cache import TurboQuantService

        svc = TurboQuantService.__new__(TurboQuantService)
        svc._available = False
        svc._default_preset = "balanced"

        stats = svc.get_compression_stats(None)
        assert stats["available"] is False
        assert stats["preset"] == "balanced"

    def test_create_cache_with_turboquant(self, monkeypatch):
        """Test cache creation when turboquantdc IS available (mocked)."""
        from services.turboquant_cache import TurboQuantService

        captured_kwargs = {}

        def mock_turbo_cache(**kw):
            captured_kwargs.update(kw)
            return types.SimpleNamespace(**kw)

        svc = TurboQuantService.__new__(TurboQuantService)
        svc._available = True
        svc._default_preset = "balanced"
        svc._default_bits = 4
        svc._fp16_window = 64

        import services.turboquant_cache as tq_mod
        monkeypatch.setattr(tq_mod, "TurboQuantCache", mock_turbo_cache)

        result = svc.create_cache(bits=3)
        assert captured_kwargs["bits"] == 3
        assert "fp16_window" not in captured_kwargs  # TurboQuantCache only takes bits
        assert result is not None


# ---------------------------------------------------------------------------
# Route-level integration tests
# ---------------------------------------------------------------------------

class TestLLMRoutes:
    """Test the LLM API routes respond correctly."""

    def test_providers_endpoint(self):
        """GET /api/llm/providers should return provider list."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from routes.llm import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        resp = client.get("/api/llm/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        assert "current" in data

    def test_turboquant_status_endpoint(self):
        """GET /api/turboquant/status should return status."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from routes.llm import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        resp = client.get("/api/turboquant/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "available" in data
        assert "presets" in data

    def test_turboquant_presets_endpoint(self):
        """GET /api/turboquant/presets should return presets."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from routes.llm import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        resp = client.get("/api/turboquant/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert "lossless" in data["presets"]
        assert "balanced" in data["presets"]

"""
backend/tests/routes/test_llm_endpoints.py

Verify LLM endpoints respond with 200 or clean 503 (not 500/ImportError).
"""
import pytest
from fastapi.testclient import TestClient

from server import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app, headers={"X-API-Key": "test-secret-key"})


def test_llm_providers_returns_200_or_503(client: TestClient):
    """GET /api/llm/providers should return 200 if LLM configured, 503 otherwise."""
    resp = client.get("/api/llm/providers")
    assert resp.status_code in (200, 503), (
        f"Expected 200 or 503, got {resp.status_code}: {resp.text}"
    )
    if resp.status_code == 200:
        data = resp.json()
        assert "providers" in data


def test_llm_analyze_trade_returns_200_or_503(client: TestClient):
    """POST /api/llm/analyze-trade should return 200 or 503 (not 500)."""
    payload = {
        "ticker": "SPY",
        "spot": 570.0,
        "regime": "positive",
        "net_gex": 1.2e9,
        "prediction": "bullish",
        "confidence": 0.65,
    }
    resp = client.post("/api/llm/analyze-trade", json=payload)
    assert resp.status_code in (200, 422, 503), (
        f"Expected 200/422/503, got {resp.status_code}: {resp.text}"
    )


def test_llm_generate_briefing_returns_200_or_503(client: TestClient):
    """POST /api/llm/generate should return 200 or 503 (not 500)."""
    payload = {
        "prompt": "Give me a short market briefing",
        "system_prompt": "You are a market analyst.",
        "max_tokens": 64,
    }
    resp = client.post("/api/llm/generate", json=payload)
    assert resp.status_code in (200, 422, 503), (
        f"Expected 200/422/503, got {resp.status_code}: {resp.text}"
    )

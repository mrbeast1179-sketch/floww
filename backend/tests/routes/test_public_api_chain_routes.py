from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


CHAIN = {
    "ticker": "SPY",
    "spot": 500.0,
    "expiries": ["2026-09-18", "2026-10-16"],
    "contracts": [
        {"expiry": "2026-09-18", "type": "call", "strike": 500.0},
        {"expiry": "2026-10-16", "type": "put", "strike": 490.0},
    ],
    "data_source": "public_api",
}


def test_public_chain_filters_requested_expiration() -> None:
    with patch(
        "routes.public_api.fetch_chain_from_public_api",
        new=AsyncMock(return_value=CHAIN.copy()),
    ):
        response = client.get("/api/public/chain/SPY?expiration=2026-09-18")

    assert response.status_code == 200
    body = response.json()
    assert body["expiries"] == ["2026-09-18"]
    assert body["n_contracts"] == 1
    assert body["contracts"][0]["expiry"] == "2026-09-18"


def test_public_chain_rejects_invalid_expiration_count() -> None:
    response = client.get("/api/public/chain/SPY?expirations=0")
    assert response.status_code == 422


def test_public_chain_returns_502_when_provider_unavailable() -> None:
    with patch(
        "routes.public_api.fetch_chain_from_public_api",
        new=AsyncMock(return_value=None),
    ):
        response = client.get("/api/public/chain/SPY")

    assert response.status_code == 502

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


@dataclass
class PortfolioFixture:
    cash: float
    positions: list[dict[str, str]]


def test_public_portfolio_returns_normalized_payload() -> None:
    account = MagicMock(account_id="acct-1")
    portfolio = PortfolioFixture(cash=1000.0, positions=[])
    broker = MagicMock()
    broker.get_trading_account.return_value = account
    broker.get_portfolio = AsyncMock(return_value=portfolio)

    with patch("routes.public_api._get_broker", new=AsyncMock(return_value=broker)):
        response = client.get("/api/public/portfolio")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["account_id"] == "acct-1"
    assert body["data_source"] == "public_api"
    assert body["portfolio"]["cash"] == 1000.0


def test_public_portfolio_returns_502_without_broker() -> None:
    with patch("routes.public_api._get_broker", new=AsyncMock(return_value=None)):
        response = client.get("/api/public/portfolio")

    assert response.status_code == 502

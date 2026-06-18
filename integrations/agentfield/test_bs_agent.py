"""
Failing-first smoke test for the additive AgentField bs_quote reasoner.

Per the brief's test discipline: this test MUST fail before
`integrations/agentfield/bs_agent.py` exists, and MUST pass after.

It exercises bs_quote in-process via httpx.AsyncClient (no network),
which is the standard way to smoke-test a FastAPI app without spinning
up a real uvicorn server. Same FastAPI object the agent exposes at
serve() time, just held in memory for the request lifecycle.

Run from the repo root:
    cd /Users/nav/Documents/GitHub/floww
    backend/.venv/bin/python3 -m pytest \
        integrations/agentfield/test_bs_agent.py -v --no-header -p no:cacheprovider
"""

from __future__ import annotations

from typing import Any, Dict

import httpx
import pytest

# This import is the test: before bs_agent.py exists, it fails with
# ModuleNotFoundError (which pytest reports as a collection/import error).
# After bs_agent.py is added, app becomes a real Agent (FastAPI subclass)
# that exposes POST /reasoners/bs_quote and returns Black-Scholes quotes.
from integrations.agentfield.bs_agent import app  # noqa: F401  -- intentional import-time assertion


SAMPLE_INPUTS: Dict[str, Any] = {
    "kind": "call",
    "S": 100.0,
    "K": 100.0,
    "T_years": 1.0,
    "sigma": 0.2,
}

# Reference values from bs_greeks.bs_call_price(100,100,1,0.2) ~= 10.18611
# (verified during precondition sweep before this test was authored; if a
# future SDK upgrade drifts the SDK's type coercion in a way that changes
# the result, this tolerance will catch it before merge).
EXPECTED_KEYS = {"price", "delta", "gamma", "vega"}
EXPECTED_PRICE_FLOOR = 10.18  # bs_call_price(100,100,1,0.2) ≈ 10.1861
EXPECTED_PRICE_CEIL = 10.19


@pytest.mark.asyncio
async def test_bs_quote_returns_valid_call_payload() -> None:
    """Hit POST /reasoners/bs_quote in-process and assert sane BS call quote."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/reasoners/bs_quote", json=SAMPLE_INPUTS)

    assert response.status_code == 200, (
        f"expected 200 from /reasoners/bs_quote, got {response.status_code}: "
        f"{response.text!r}"
    )

    payload = response.json()
    assert isinstance(payload, dict), f"expected dict payload, got {type(payload).__name__}"
    assert EXPECTED_KEYS.issubset(payload.keys()), (
        f"missing greek keys in {sorted(payload.keys())}; "
        f"need at least {sorted(EXPECTED_KEYS)}"
    )

    price = float(payload["price"])
    assert EXPECTED_PRICE_FLOOR <= price <= EXPECTED_PRICE_CEIL, (
        f"bs_call_price(100,100,1,0.2) = {price}, "
        f"expected in [{EXPECTED_PRICE_FLOOR}, {EXPECTED_PRICE_CEIL}]"
    )

    for greek in ("delta", "gamma", "vega"):
        value = float(payload[greek])
        assert 0.0 < value < 50.0, f"{greek}={value} out of sanity range"
        assert value == value, f"{greek} is NaN"


@pytest.mark.asyncio
async def test_bs_quote_control_plane_compat_route() -> None:
    """The co-located /api/v1/execute/{node}.{func} proxy returns the same payload shape.

    The AgentField control plane (Go) normally exposes this path. Because no
    Go control plane binary is present in this environment, the path is
    re-implemented as a thin FastAPI proxy on the Agent itself. This test
    asserts that proxy route produces a real BS quote end-to-end (not a
    stub / 404). Disclosed in reports/agentfield_poc_<date>.md.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/execute/floww_greeks.bs_quote",
            json=SAMPLE_INPUTS,
        )

    assert response.status_code == 200, (
        f"expected 200 from /api/v1/execute/floww_greeks.bs_quote, "
        f"got {response.status_code}: {response.text!r}"
    )
    payload = response.json()
    assert isinstance(payload, dict)
    assert EXPECTED_KEYS.issubset(payload.keys())


@pytest.mark.asyncio
async def test_bs_quote_rejects_unknown_reasoner_via_compat_route() -> None:
    """The compat proxy must 404 when the node.func combo isn't registered."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/execute/floww_greeks.nonexistent_reasoner",
            json=SAMPLE_INPUTS,
        )
    assert response.status_code == 404, (
        f"unknown reasoner should 404, got {response.status_code}"
    )

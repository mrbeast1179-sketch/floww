"""
Tests for the additive AgentField POC adapter.

Iter 1 had THREE test cases:
  - in-process /reasoners/bs_quote sanity (kept)
  - co-located /api/v1/execute/... proxy (REMOVED in iter 2 — proxy is
    replaced by the real Go control plane)
  - co-located 404 (REMOVED in iter 2 — same reason)

Iter 2:
  - SAME sanity test for the in-process reasoner (proves SDK wiring +
    pure-math correctness without needing the plane).
  - NEW live network test gated by `AGENTFIELD_LIVE_TEST=1`. When set,
    it asserts that `POST :8080/api/v1/execute/floww_greeks.bs_quote`
    against the real Go control plane dispatches to :8002 and returns
    a valid BS quote. Without that env var, the test skips so it
    doesn't flake in environments without a running control plane.

Run from repo root:
    cd /Users/nav/Documents/GitHub/floww
    backend/.venv/bin/python3 -m pytest \
        integrations/agentfield/test_bs_agent.py -v --no-header -p no:cacheprovider

Live variant (iterate 2 evidence):
    AGENTFIELD_LIVE_TEST=1 \
    backend/.venv/bin/python3 -m pytest \
        integrations/agentfield/test_bs_agent.py -v --no-header -p no:cacheprovider
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict

import httpx
import pytest
from scipy.stats import norm

# Import-time discipline: before bs_agent.py existed the test failed
# with ModuleNotFoundError at collection; now `app` is a real Agent.
from integrations.agentfield.bs_agent import app  # noqa: F401  -- intentional import-time assertion


SAMPLE_INPUTS: Dict[str, Any] = {
    "kind": "call",
    "S": 100.0,
    "K": 100.0,
    "T_years": 1.0,
    "sigma": 0.2,
}
EXPECTED_KEYS = {"price", "delta", "gamma", "vega"}
# Reference: bs_call_price(100,100,1,0.2) ≈ 10.1861.
# Loose tolerance -> catches a schema drift without flaking on noise.
EXPECTED_PRICE_FLOOR = 10.18
EXPECTED_PRICE_CEIL = 10.19


@pytest.mark.asyncio
async def test_bs_quote_returns_valid_call_payload() -> None:
    """In-process /reasoners/bs_quote sanity check (always runs)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/reasoners/bs_quote", json=SAMPLE_INPUTS)
    assert response.status_code == 200, (
        f"expected 200 from /reasoners/bs_quote, got {response.status_code}: "
        f"{response.text!r}"
    )
    payload = response.json()
    assert isinstance(payload, dict)
    assert EXPECTED_KEYS.issubset(payload.keys()), payload
    price = float(payload["price"])
    assert EXPECTED_PRICE_FLOOR <= price <= EXPECTED_PRICE_CEIL, price
    for greek in ("delta", "gamma", "vega"):
        value = float(payload[greek])
        assert 0.0 < value < 50.0, f"{greek}={value} out of sanity range"
        assert value == value, f"{greek} is NaN"


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("AGENTFIELD_LIVE_TEST"),
    reason="set AGENTFIELD_LIVE_TEST=1 when the Go control plane is running on :8080 and the agent is registered on :8002",
)
async def test_real_control_plane_dispatch_live() -> None:
    """Hit POST :8080/api/v1/execute/floww_greeks.bs_quote against the REAL Go control plane.

    Path: client -> Go control plane (8080) -> agent (8002 /reasoners/bs_quote) -> backend.bs_greeks.

    Requires:
      - Go toolchain installed (`brew install go`)
      - Control plane running: `cd /Users/nav/GitHub/agentfield/control-plane
        && PATH=/Users/nav/.local/bin:$PATH go run ./cmd/af dev --port 8080`
      - Agent running: `backend/.venv/bin/python3 integrations/agentfield/bs_agent.py`
      - export AGENTFIELD_LIVE_TEST=1 before pytest

    The Go control plane is expected to validate node_id "floww_greeks"
    against its registry, then dispatch the call to the agent.
    """
    base = os.getenv("AGENTFIELD_CONTROL_PLANE", "http://127.0.0.1:8080")
    async with httpx.AsyncClient(base_url=base) as client:
        response = await client.post(
            "/api/v1/execute/floww_greeks.bs_quote",
            json=SAMPLE_INPUTS,
        )
    assert response.status_code == 200, (
        f"expected 200 from real Go plane, got {response.status_code}: "
        f"{response.text!r}"
    )
    payload = response.json()
    assert isinstance(payload, dict)
    assert EXPECTED_KEYS.issubset(payload.keys()), payload
    price = float(payload["price"])
    assert EXPECTED_PRICE_FLOOR <= price <= EXPECTED_PRICE_CEIL, price


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("AGENTFIELD_LIVE_TEST"),
    reason="set AGENTFIELD_LIVE_TEST=1 when the Go control plane is running on :8080 and the agent is registered on :8002",
)
async def test_real_control_plane_dispatch_unknown_reasoner() -> None:
    """The real Go plane returns 404 for an unregistered function on a known node."""
    base = os.getenv("AGENTFIELD_CONTROL_PLANE", "http://127.0.0.1:8080")
    async with httpx.AsyncClient(base_url=base) as client:
        response = await client.post(
            "/api/v1/execute/floww_greeks.nonexistent_reasoner",
            json=SAMPLE_INPUTS,
        )
    assert response.status_code in (404, 422), (
        f"unknown reasoner should 404/422, got {response.status_code}: "
        f"{response.text!r}"
    )


@pytest.mark.asyncio
async def test_bs_vomma_returns_valid_payload() -> None:
    """In-process ``/reasoners/bs_vomma`` sanity check (always runs).

    Ground truth is the **closed-form** Black-Scholes vomma computed
    INDEPENDENTLY from scipy + math in this file (not via the wrapper's
    internal upstream call). Catches:
      - wrong-argument wiring (e.g. S↔K, sigma↔T_years),
      - wrong-function wiring (anyone who substitutes bs_zomma/bs_gamma/
        bs_vega for bs_vomma — these return values very different from
        the closed-form ~9.85 for S=K=100, T=1y, sigma=0.2),
      - missing input normalization.

    Tight absolute tolerance (1e-9) is safe in double-precision.
    """
    inputs = {"S": 100.0, "K": 100.0, "T_years": 1.0, "sigma": 0.2, "r": 0.05, "q": 0.0}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/reasoners/bs_vomma", json=inputs)
    assert response.status_code == 200, (
        f"expected 200 from /reasoners/bs_vomma, got {response.status_code}: "
        f"{response.text!r}"
    )
    payload = response.json()
    assert isinstance(payload, dict)
    assert {"vomma"} == set(payload.keys()), (
        f"vomma wrapper should return ONLY {{'vomma'}}, got {sorted(payload.keys())}"
    )
    actual = float(payload["vomma"])
    # Independent closed-form: vega * d1 * d2 / sigma
    d1 = (math.log(inputs["S"] / inputs["K"])
          + (inputs["r"] - inputs["q"] + 0.5 * inputs["sigma"] ** 2)
            * inputs["T_years"]) / (inputs["sigma"] * math.sqrt(inputs["T_years"]))
    d2 = d1 - inputs["sigma"] * math.sqrt(inputs["T_years"])
    vega = (inputs["S"] * math.exp(-inputs["q"] * inputs["T_years"])
            * norm.pdf(d1) * math.sqrt(inputs["T_years"]))
    expected = vega * d1 * d2 / inputs["sigma"]
    assert abs(actual - expected) < 1e-9, (
        f"wrapper returned vomma={actual}, expected {expected} (closed-form BS vomma)"
    )
    assert actual == actual, "vomma is NaN"  # NaN guard


@pytest.mark.asyncio
async def test_bs_vomma_handles_degenerate_input() -> None:
    """In-process ``/reasoners/bs_vomma`` degenerate-input check.

    For S <= 0 the upstream ``bs_vomma`` returns 0.0 (silent-zero
    convention). The wrapper must surface the same 200-with-zeros
    envelope rather than 4xx-ing on the degenerate case, so floww's
    analytics surfaces stay numerically aligned with ``bs_quote``.
    """
    inputs = {"S": 0.0, "K": 100.0, "T_years": 1.0, "sigma": 0.2, "r": 0.05, "q": 0.0}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/reasoners/bs_vomma", json=inputs)
    assert response.status_code == 200, (
        f"degenerate input should 200-with-zeros, got {response.status_code}: "
        f"{response.text!r}"
    )
    payload = response.json()
    assert payload == {"vomma": 0.0}, payload

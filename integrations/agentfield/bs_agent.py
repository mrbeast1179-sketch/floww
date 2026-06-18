"""
Additive AgentField PoC adapter for floww's Black-Scholes module.
Iteration 2 — registered against the REAL AgentField Go control plane.

Iter 1 (now superseded) demonstrated an in-process @app.reasoner with a
co-located `/api/v1/execute/{node}.{func}` proxy mounted on the Agent's
FastAPI instance itself, because no Go toolchain was available in the
environment. Iter 2 replaces that proxy with a true control-plane
dispatch path; iter 3 widens the surface to two reasoners:

  client → :8080/api/v1/execute/floww_greeks.{bs_quote,bs_vomma}
        → AgentField Go control plane (af dev)
        → :8002/reasoners/{bs_quote,bs_vomma}  (this Agent)
        → backend/bs_greeks.py  (read-only)

Two reasoners ship together (both registered against the same
``floww_greeks`` node_id, both visible in
``GET /api/v1/discovery/capabilities`` on the real CP):
  - ``bs_quote``  call/put pricing + first-order Greeks (delta,
                    gamma, vega). Symmetric schema under ``kind``.
  - ``bs_vomma``  higher-order ∂²Price/∂σ² (= dVega/dSigma).
                    Symmetric for call/put, useful in vol-of-vol
                    surfaces and risk reports.

To start the plane: brew install go && cd /Users/nav/GitHub/agentfield/control-plane
   && PATH=/Users/nav/.local/bin:$PATH go run ./cmd/af dev --port 8080
(The `python` shim in /Users/nav/.local/bin/python points at the backend
venv python3; the control plane's dev service shells out to `python`
during init.) With PATH including that shim, the plane binds :8080 in
dev (SQLite) mode in ~15 s on a warm Go cache.

Additive constraints (verified):
- No edits to `backend/`, `frontend/`, `kanban/`, `project_oracle/`.
- Pre-existing WIP untouched.
- Read-only import of `backend/bs_greeks.py`; never mutated.
- Paper / analytics only — no live order execution.

Known limitation (NOT a blocker for the PoC, flagged for next iter):
- `app.serve()` would also call `await app.agent.connection_manager.start()`
  to open a WebSocket to the control plane for push-style triggers.
  Our `uvicorn.run(...)` launcher does NOT call connection_manager.start
  — pure curl-driven POST /api/v1/execute/... works, but event triggers /
  schedule triggers from the plane will not. If push dispatch becomes a
  requirement, add `await app.connection_manager.start()` to the startup
  hook below.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Dict

# Make `backend.bs_greeks` importable. Layout invariant: this directory
# must live at <repo>/integrations/agentfield/, a direct sibling of
# <repo>/backend/. If reorganised, the import will fail fast at
# module-load time with ModuleNotFoundError.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "backend"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Read-only import: pure functions; no shared mutable state.
from bs_greeks import (  # noqa: E402  -- sys.path injection above is intentional
    bs_call_price,
    bs_delta,
    bs_gamma,
    bs_put_price,
    bs_vega,
    bs_vomma as upstream_bs_vomma,  # renamed (no leading underscore) so the test file can reference it as a public upstream binding
)

from agentfield import Agent, AIConfig  # noqa: E402  -- editable install in backend venv
from fastapi import HTTPException  # noqa: E402

log = logging.getLogger("integrations.agentfield.bs_agent")

# ──────────────────────────────────────────────────────────────────────
# Agent definition
# ──────────────────────────────────────────────────────────────────────
#
# node_id = "floww_greeks" — routing key the Go control plane uses to
# reach this reasoner. Kept distinct from agentfield_hub's
# `floww-trading` so the two coexist without registration collisions.
#
# dev_mode=False (iter 2): drops the SDK's DEBUG-level chatter so
# `agent_workflow` events are easy to read in the live curl trace.

app = Agent(
    node_id="floww_greeks",
    version="1.0.0",
    ai_config=AIConfig(model="local"),
    dev_mode=False,
)


# ──────────────────────────────────────────────────────────────────────
# Reasoner
# ──────────────────────────────────────────────────────────────────────
#
# Iter 2 regression fix (reviewer finding #1): `raise HTTPException(...)`
# instead of `raise ValueError(...)`. The reasoner runs through the
# SDK's `_execute_reasoner_endpoint`, which preserves HTTPException as
# a structured 4xx response; generic exceptions are converted to 500.
# The 400 contract is the one callers expect for malformed `kind`.

@app.reasoner(tags=["floww", "greeks", "poc"])
async def bs_quote(
    kind: str,
    S: float,
    K: float,
    T_years: float,
    sigma: float,
    r: float = 0.045,
    q: float = 0.0,
) -> Dict[str, Any]:
    """Compute a Black-Scholes call/put quote with the first-order Greeks.

    Inputs (conventions match floww's analytics surfaces):
        - S : spot price of the underlying
        - K : strike price
        - T_years : time to expiry in YEARS
        - sigma : annualised implied volatility (decimal, e.g. 0.2 for 20%)

    Returns price + first-order Greeks. Pure computation only — no IO,
    no shared state, paper/sim safe.
    """
    kind_norm = kind.lower().strip()
    if kind_norm not in ("call", "put"):
        # Structured 4xx — preserved by SDK's `_execute_reasoner_endpoint`
        # and propagated by the control plane back to the curl caller.
        raise HTTPException(400, f"kind must be 'call' or 'put', got {kind!r}")

    # Numeric guards: mirror bs_greeks.py's 0.0-on-degenerate convention.
    if T_years <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {
            "kind": kind_norm,
            "price": 0.0,
            "delta": 0.0,
            "gamma": 0.0,
            "vega": 0.0,
        }

    if kind_norm == "call":
        price = bs_call_price(S, K, T_years, sigma, r=r, q=q)
    else:
        price = bs_put_price(S, K, T_years, sigma, r=r, q=q)

    delta = bs_delta(S, K, T_years, sigma, q=q, kind=kind_norm, r=r)
    gamma = bs_gamma(S, K, T_years, sigma, q=q, r=r)
    vega = bs_vega(S, K, T_years, sigma, q=q, r=r)

    return {
        "kind": kind_norm,
        "price": float(price),
        "delta": float(delta),
        "gamma": float(gamma),
        "vega": float(vega),
    }


@app.reasoner(tags=["floww", "greeks", "poc", "vomma"])
async def bs_vomma(
    S: float,
    K: float,
    T_years: float,
    sigma: float,
    r: float = 0.05,
    q: float = 0.0,
) -> Dict[str, Any]:
    """Black-Scholes vomma (∂²Price/∂σ²) = ``vega * d1 * d2 / sigma``.

    Higher-order Greek measuring the sensitivity of vega to a move in
    implied volatility — useful in vol-of-vol surfaces and risk reports
    where a first-order gamma/vega profile alone is insufficient.

    Inputs use the same conventions as ``bs_quote``:

        - ``S`` : spot price of the underlying
        - ``K`` : strike price
        - ``T_years`` : time-to-expiry in years
        - ``sigma`` : annualised IV (decimal, e.g. ``0.2`` for 20%)

    Returns ``{"vomma": float}``. Degenerate inputs (S/K/T_years/sigma <= 0)
    and masked numerical errors yield ``{"vomma": 0.0}`` — matches
    ``backend/bs_greeks.py``'s silent-zero convention.

    Same dependent-clean guarantee as ``bs_quote``: pure computation,
    no IO, no shared state, paper/analytics safe.
    """
    # Upstream bs_vomma already enforces the degenerate-input guard and
    # masks numerical errors via _mask_zero; no need to pre-replicate.
    # `r=0.05` default in the wrapper matches bs_vomma's upstream
    # default — intentional non-override so callers can omit `r` and
    # get the same value from the wrapper or the bare function.
    vomma = upstream_bs_vomma(S, K, T_years, sigma, q=q, r=r)
    return {"vomma": float(vomma)}


# ──────────────────────────────────────────────────────────────────────
# Real-control-plane registration hook (iter 2 — replaces compat proxy)
# ──────────────────────────────────────────────────────────────────────
#
# On uvicorn startup, advertise this agent to the Go control plane on
# :8080 and start the heartbeat thread so the registration lease stays
# fresh. Both calls resolve on `app.agentfield_handler` (see SDK
# agent_field_handler.py line 41 + 265).
#
# Iter 2 review fix #2: bounded the registration await with
# asyncio.wait_for(timeout=10.0) so a TCP-firewalled / hung plane
# cannot pin uvicorn startup forever. Fall back to heartbeat retry.

@app.on_event("startup")
async def _register_with_real_control_plane() -> None:
    """One-shot registration + heartbeat against the real Go control plane."""
    control_plane_url = os.getenv("AGENTFIELD_SERVER", "http://127.0.0.1:8080")
    app.agentfield_server = control_plane_url
    app.base_url = "http://127.0.0.1:8002"
    log.info("registering node_id=%s against control plane %s",
             app.node_id, control_plane_url)
    try:
        await asyncio.wait_for(
            app.agentfield_handler.register_with_agentfield_server(8002),
            timeout=10.0,
        )
        log.info("registration: ok")
    except asyncio.TimeoutError:
        # Plane is hung / firewall-dropping — heartbeat will retry lease.
        log.warning("registration timed out after 10s; relying on heartbeat retry")
    except Exception as exc:
        log.warning("registration failed (will retry via heartbeat): %s", exc)
    # 30s default interval matches `af`'s expected heartbeat cadence.
    app.agentfield_handler.start_heartbeat()


# ──────────────────────────────────────────────────────────────────────
# Entrypoint (iter 2 — uvicorn direct; bypasses SDK app.serve() bug)
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # `app.serve(port=8002)` is broken on this uvicorn+websockets combo
    # (KeyError: 'websockets-sansio'); uvicorn.run() against the FastAPI
    # subclass is the minimum-blast-radius workaround. The @app.on_event
    # startup hook fires identically, and the agent's auto-REST routes
    # (`/reasoners/...`) are already attached to the Agent instance at
    # decoration time.
    import uvicorn
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8002,
        log_level="info",
        access_log=False,
    )

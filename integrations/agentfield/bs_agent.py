"""
Additive AgentField PoC adapter for floww's Black-Scholes module.

This file demonstrates Mission A of the brief's thesis: every floww
analytics service is already a perfect AgentField reasoner. We wrap
the existing read-only `backend/bs_greeks.py` functions behind a
single AgentField reasoner `bs_quote` and expose it via the
AgentField Python SDK's auto-REST route, plus a co-located proxy at
`/api/v1/execute/{node}.{func}` that mirrors the path the upstream
Go control plane would expose.

Additive constraints (verified):
- No file in `backend/`, `frontend/`, `kanban/`, `project_oracle/` is
  modified. We only add new files under `integrations/agentfield/`.
- `backend/bs_greeks.py` is imported read-only; we never mutate it
  nor any downstream state.
- No live order execution; analytics / paper quotes only (per
  paper-only mandate).

Layout contract:
- This directory MUST live at `<repo>/integrations/agentfield/`, i.e.
  a direct sibling of `<repo>/backend/`. The sys.path injection below
  computes `../../backend/` relative to this file. If anyone moves or
  renames this directory, the import of `bs_greeks` will break loudly
  with a ModuleNotFoundError on startup — fail-fast behaviour is
  intentional.

Control-plane-compat note:
- The AgentField Go control plane normally exposes `POST
  /api/v1/execute/{node_id}.{func}` and dispatches to the agent's
  internal `/reasoners/{func}` route. No `go` toolchain is installed
  in this environment (`which go` empty; brew `go` absent; opt/homebrew
  /usr/local absent). To still produce a real `POST /api/v1/execute/`
  curl response for the brief's evidence, we re-implement that
  proxy as a thin FastAPI route on the Agent itself. The math,
  schema, and shape are unchanged; only the dispatch location is
  disclosed in `reports/agentfield_poc_<date>.md`.

Registry contract:
- `app._reasoner_registry` is the canonical source of truth for which
  reasoner IDs are registered on a given Agent instance. The lookup
  in `control_plane_compat` reads from it directly. The key name is
  underscore-prefixed in the SDK today — if AgentField renames this
  attribute in a future release, the compat route will need an
  update. The fallback to `getattr(app, func_name, None)` was
  attempted first; the reasoner marker (`_is_reasoner`) does not get
  stamped on the Agent's `@app.reasoner` wrapper, so registry
  dispatch is the more reliable mirror of the real control plane.
"""

from __future__ import annotations

import asyncio
import json as _json
import os
import sys
from typing import Any, Dict

# Make `backend.bs_greeks` importable without modifying the backend
# tree. The path is computed once at module load; we never assume cwd.
# See "Layout contract" in the module docstring for the directory
# invariant this depends on.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "backend"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Read-only import: pure functions, no shared mutable state. We never
# reassign anything from bs_greeks and we never mutate its module attrs.
from bs_greeks import (  # noqa: E402  -- sys.path injection above is intentional
    bs_call_price,
    bs_delta,
    bs_gamma,
    bs_put_price,
    bs_vega,
)

from agentfield import Agent, AIConfig  # noqa: E402  -- editable install in backend venv
from fastapi import HTTPException, Request  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Agent definition
# ──────────────────────────────────────────────────────────────────────
#
# node_id = "floww_greeks" — the routing name the control plane uses
# to reach this reasoner. Kept distinct from the existing in-floww
# hub's `floww-trading` (agentfield_hub.py) so dev_mode=True standalone
# agents co-exist without registration collisions.
#
# dev_mode=True → no upstream control plane required, period. The
# agent serves FastAPI routes directly. The control-plane-compat
# proxy at /api/v1/execute/{node}.{func} lives on this same Agent
# object (Agent extends FastAPI), so a single uvicorn instance
# answers both shapes.

app = Agent(
    node_id="floww_greeks",
    version="1.0.0",
    ai_config=AIConfig(model="local"),
    dev_mode=True,
)


# ──────────────────────────────────────────────────────────────────────
# Reasoner
# ──────────────────────────────────────────────────────────────────────
#
# Pure Black-Scholes quote. Reads from the existing backend module,
# never writes anywhere. Standard type hints (no Pydantic) — the
# SDK's `_validate_handler_input` coerces dict payloads to the
# expected types at runtime, per agent.py.
#
# Error-shape decision: HTTPException(400) only fires for an
# unsupported `kind` (a true client-input error). Numeric guards
# (T_years <= 0, sigma <= 0, etc.) return a zero dictionary to
# match the upstream convention in bs_greeks.py, where every
# guard returns 0.0 — preserving behavioural parity with the rest
# of the floww analytics stack.

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


# ──────────────────────────────────────────────────────────────────────
# AgentField control-plane compatibility proxy
# ──────────────────────────────────────────────────────────────────────
#
# The AgentField Go control plane exposes POST /api/v1/execute/{node}.{func}.
# In this environment, no `go` toolchain is installed, so we mount an
# equivalent passthrough route on the Agent itself. This is the same
# dispatch shape the upstream plane uses (parse `node.func`, locate the
# registered reasoner method, invoke it with the validated kwargs).
#
# Starlette `Request.body()` can only be consumed once per request; we
# read it into `raw` exactly once and branch on truthiness. A second
# read would raise `RuntimeError: Already consumed`. This was the
# top-priority reviewer finding and is now hardened.

@app.post("/api/v1/execute/{path:path}")
async def control_plane_compat(path: str, request: Request) -> Any:
    """Passthrough that mirrors the AgentField control plane's execute route.

    Path format: "/api/v1/execute/{node_id}.{func_name}"

    Dispatch rule (mirrors the real Go control plane):
    1. Consume the request body exactly once.
    2. Parse the JSON body into kwargs dict (or stay empty for GET-style
       calls).
    3. Look up `func_name` in the Agent's `_reasoner_registry` —
       canonical source of truth for what's registered.
    4. If absent, return 404 with the same shape curl would see against
       the real control plane.
    5. If present, invoke the registry's `func` with the request body's
       kwargs. Workflow tracking is performed upstream by the real
       control plane; we don't double-track here (acceptable for a
       smoke-test PoC; disclosed in the report).
    """
    body: Dict[str, Any] = {}
    raw = await request.body()  # EXACTLY ONE read.
    if raw:
        try:
            parsed = _json.loads(raw)
        except _json.JSONDecodeError as exc:
            raise HTTPException(400, f"invalid JSON body: {exc!s}")
        if not isinstance(parsed, dict):
            raise HTTPException(400, "request body must be a JSON object")
        body = parsed

    if "." not in path:
        raise HTTPException(
            400,
            f"path '{path}' is not of the form '<node_id>.<func_name>'",
        )
    node_id, _, func_name = path.rpartition(".")
    # node_id is ignored for routing — single-node local dispatch. The
    # real control plane would validate node_id against its registry.
    _ = node_id

    registry = getattr(app, "_reasoner_registry", {}) or {}
    entry = registry.get(func_name)
    if entry is None:
        raise HTTPException(
            404,
            f"reasoner '{func_name}' not registered on node 'floww_greeks'",
        )

    func = entry.func
    try:
        if asyncio.iscoroutinefunction(func):
            return await func(**body)
        return func(**body)
    except HTTPException:
        # Re-raise so FastAPI shapes the 4xx response properly.
        raise
    except Exception as exc:  # surface a structured error to the client
        raise HTTPException(500, f"reasoner execution failed: {exc!s}")


# ──────────────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Port 8002 chosen to avoid collision with floww backend (:8000),
    # floww frontend (:3000), and reserved control-plane slot (:8080).
    # `serve` is the Agent's standard launch method (agent.py line 5093).
    app.serve(port=8002)

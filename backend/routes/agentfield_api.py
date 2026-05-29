"""
routes/agentfield_api.py

REST API routes for the AgentField integration.

Exposes:
  GET  /agentfield/v1/status          — hub status + cost tracker
  GET  /agentfield/v1/signals/gex     — GEX regime
  GET  /agentfield/v1/signals/alerts  — alert scan
  GET  /agentfield/v1/signals/vpin    — VPIN value
  GET  /agentfield/v1/signals/hawkes  — Hawkes state
  GET  /agentfield/v1/risk/greeks     — portfolio Greeks
  GET  /agentfield/v1/risk/scenario   — what-if scenario
  GET  /agentfield/v1/risk/size       — position sizing
  GET  /agentfield/v1/briefing/build  — build briefing
  GET  /agentfield/v1/briefing/classify — regime classify
  GET  /agentfield/v1/data/chain      — option chain
  GET  /agentfield/v1/data/vol-surface — vol surface
  POST /agentfield/v1/execute/order   — submit paper order
  GET  /agentfield/v1/execute/health  — execution health
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Any, Dict

router = APIRouter()


def _hub():
    from services.agentfield_hub import get_hub  # type: ignore

    return get_hub()


@router.get("/agentfield/v1/status")
async def agentfield_status() -> Dict[str, Any]:
    hub = _hub()
    return {
        "status": "ok" if hub._initialized else "not_initialized",
        "node_id": "floww-trading",
        "version": "1.0.0",
        "cost_total_usd": hub.cost_tracker.total_cost_usd,
        "cost_total_tokens": hub.cost_tracker.total_tokens,
    }


@router.get("/agentfield/v1/signals/gex")
async def signal_gex(ticker: str = Query(default="SPY", min_length=1, max_length=10)) -> Dict[str, Any]:
    hub = _hub()
    result = await hub.agent.call("floww-trading.gex-regime", input={"ticker": ticker})
    return result


@router.get("/agentfield/v1/signals/alerts")
async def signal_alerts(ticker: str = Query(default="SPY", min_length=1, max_length=10)) -> Dict[str, Any]:
    hub = _hub()
    result = await hub.agent.call("floww-trading.scan-alerts", input={"ticker": ticker})
    return result


@router.get("/agentfield/v1/signals/vpin")
async def signal_vpin(ticker: str = Query(default="SPY", min_length=1, max_length=10)) -> Dict[str, Any]:
    hub = _hub()
    result = await hub.agent.call("floww-trading.vpin-signal", input={"ticker": ticker})
    return result


@router.get("/agentfield/v1/signals/hawkes")
async def signal_hawkes(ticker: str = Query(default="SPY", min_length=1, max_length=10)) -> Dict[str, Any]:
    hub = _hub()
    result = await hub.agent.call("floww-trading.hawkes-intensity", input={"ticker": ticker})
    return result


@router.get("/agentfield/v1/risk/greeks")
async def risk_greeks(
    name: str = Query(default="main"),
    spot: float = Query(default=0.0, ge=0),
    iv: float = Query(default=0.15, ge=0, le=5),
) -> Dict[str, Any]:
    hub = _hub()
    result = await hub.agent.call("floww-trading.portfolio-greeks", input={"name": name, "spot": spot, "iv": iv})
    return result


@router.get("/agentfield/v1/risk/scenario")
async def risk_scenario(
    name: str = Query(default="main"),
    spot_shock: float = Query(default=0.0),
    vol_shock: float = Query(default=0.0),
    time_decay_days: int = Query(default=1, ge=0, le=30),
) -> Dict[str, Any]:
    hub = _hub()
    result = await hub.agent.call(
        "floww-trading.scenario-analysis",
        input={"name": name, "spot_shock": spot_shock, "vol_shock": vol_shock, "time_decay_days": time_decay_days},
    )
    return result


@router.get("/agentfield/v1/risk/size")
async def risk_size(
    account_size: float = Query(default=5000.0, gt=0),
    risk_per_trade_pct: float = Query(default=0.02, gt=0, le=0.5),
    spot: float = Query(default=0.0, ge=0),
    gex_level: float = Query(default=0.0),
) -> Dict[str, Any]:
    hub = _hub()
    result = await hub.agent.call(
        "floww-trading.position-size",
        input={"account_size": account_size, "risk_per_trade_pct": risk_per_trade_pct, "spot": spot, "gex_level": gex_level},
    )
    return result


@router.get("/agentfield/v1/briefing/build")
async def briefing_build(ticker: str = Query(default="SPY", min_length=1, max_length=10)) -> Dict[str, Any]:
    hub = _hub()
    result = await hub.agent.call("floww-trading.build-briefing", input={"ticker": ticker})
    return result


@router.get("/agentfield/v1/briefing/classify")
async def briefing_classify(
    net_gex: float = Query(default=0.0),
    call_oi: float = Query(default=0),
    put_oi: float = Query(default=0),
    iv_skew: float = Query(default=0.0),
    flip_level: float = Query(default=0.0),
    spot: float = Query(default=0.0),
) -> Dict[str, Any]:
    hub = _hub()
    result = await hub.agent.call(
        "floww-trading.classify-regime",
        input={"net_gex": net_gex, "call_oi": call_oi, "put_oi": put_oi, "iv_skew": iv_skew, "flip_level": flip_level, "spot": spot},
    )
    return result


@router.get("/agentfield/v1/data/chain")
async def data_chain(ticker: str = Query(default="SPY", min_length=1, max_length=10)) -> Dict[str, Any]:
    hub = _hub()
    result = await hub.agent.call("floww-trading.option-chain", input={"ticker": ticker})
    return result


@router.get("/agentfield/v1/data/vol-surface")
async def data_vol_surface(ticker: str = Query(default="SPY", min_length=1, max_length=10)) -> Dict[str, Any]:
    hub = _hub()
    result = await hub.agent.call("floww-trading.vol-surface", input={"ticker": ticker})
    return result


@router.post("/agentfield/v1/execute/order")
async def execute_order(order: Dict[str, Any]) -> Dict[str, Any]:
    hub = _hub()
    result = await hub.agent.call("floww-trading.submit-order", input={"order": order})
    return result


@router.get("/agentfield/v1/execute/health")
async def execute_health() -> Dict[str, Any]:
    hub = _hub()
    result = await hub.agent.call("floww-trading.execution-health", input={})
    return result

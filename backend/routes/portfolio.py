"""
backend/routes/portfolio.py

Portfolio management routes.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path

router = APIRouter()


@router.get("/portfolio/{name}")
async def get_portfolio(name: str):
    from server import db
    portfolio = db.portfolios.find_one({"name": name}, {"_id": 0})
    if not portfolio:
        raise HTTPException(404, f"Portfolio '{name}' not found")
    return portfolio


@router.post("/portfolio/{name}/position")
async def add_position(name: str, position: dict):
    from server import db
    from datetime import datetime, timezone
    position["added_at"] = datetime.now(timezone.utc).isoformat()
    result = db.portfolios.update_one(
        {"name": name},
        {"$push": {"positions": position}},
        upsert=True,
    )
    return {"status": "ok", "modified": result.modified_count}


@router.delete("/portfolio/{name}/position/{index}")
async def remove_position(name: str, index: int = Path(..., ge=0)):
    from server import db
    portfolio = db.portfolios.find_one({"name": name})
    if not portfolio:
        raise HTTPException(404, f"Portfolio '{name}' not found")
    positions = portfolio.get("positions", [])
    if index >= len(positions):
        raise HTTPException(400, f"Invalid position index {index}")
    positions.pop(index)
    db.portfolios.update_one({"name": name}, {"$set": {"positions": positions}})
    return {"status": "ok"}


@router.get("/portfolio/{name}/scenario")
async def scenario(name: str, spot_change_pct: float = 0.0):
    from server import db
    from server import calc_portfolio_scenario
    portfolio = db.portfolios.find_one({"name": name})
    if not portfolio:
        raise HTTPException(404, f"Portfolio '{name}' not found")
    result = await calc_portfolio_scenario(portfolio, spot_change_pct)
    return result


@router.post("/portfolio/{name}/hedge")
async def hedge(name: str, hedge_request: dict):
    from server import db
    from server import calc_hedge_recommendation
    portfolio = db.portfolios.find_one({"name": name})
    if not portfolio:
        raise HTTPException(404, f"Portfolio '{name}' not found")
    result = await calc_hedge_recommendation(portfolio, hedge_request)
    return result


@router.post("/position-size")
async def position_size(request: dict):
    from server import calc_position_size
    result = calc_position_size(
        account_value=request.get("account_value", 100000),
        risk_pct=request.get("risk_pct", 0.02),
        entry_price=request.get("entry_price", 0),
        stop_price=request.get("stop_price", 0),
    )
    return result

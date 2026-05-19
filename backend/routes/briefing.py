"""
backend/routes/briefing.py

Briefing routes.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path

router = APIRouter()


@router.get("/api/briefing/{ticker}")
async def briefing(ticker: str):
    from server import generate_briefing
    result = await generate_briefing(ticker.upper())
    return result


@router.get("/api/briefing/{ticker}/html")
async def briefing_html(ticker: str):
    from server import generate_briefing_html
    result = await generate_briefing_html(ticker.upper())
    return result


@router.post("/api/briefing/{ticker}/send")
async def briefing_send(ticker: str, request: dict):
    from server import send_briefing
    result = await send_briefing(ticker.upper(), request)
    return result

"""
backend/routes/llm.py

LLM analysis routes.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/api/llm/analyze-trade")
async def llm_analyze_trade(request: dict):
    from server import llm_analyze_trade_handler
    result = await llm_analyze_trade_handler(request)
    return result


@router.post("/api/llm/generate-briefing")
async def llm_generate_briefing(request: dict):
    from server import llm_generate_briefing_handler
    result = await llm_generate_briefing_handler(request)
    return result


@router.get("/api/llm/providers")
async def llm_providers():
    from server import get_llm_providers
    return get_llm_providers()

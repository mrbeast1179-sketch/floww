"""
backend/routes/llm.py

LLM analysis routes.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/llm/analyze-trade")
async def llm_analyze_trade(request: dict):
    """Analyze a trade opportunity using LLM."""
    try:
        from services.llm import analyze_trade_with_llm
        ticker = request.get("ticker", "")
        spot = request.get("spot", 0.0)
        regime = request.get("regime", "unknown")
        net_gex = request.get("net_gex", 0.0)
        prediction = request.get("prediction", "")
        confidence = request.get("confidence", 0.0)
        result = await analyze_trade_with_llm(
            ticker=ticker,
            spot=spot,
            regime=regime,
            net_gex=net_gex,
            prediction=prediction,
            confidence=confidence,
        )
        return result
    except ImportError:
        raise HTTPException(status_code=503, detail="LLM not configured")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/llm/generate-briefing")
async def llm_generate_briefing(request: dict):
    """Generate a morning briefing using LLM."""
    try:
        from services.llm import get_llm_service
        llm = get_llm_service()
        prompt = request.get("prompt", "")
        system_prompt = request.get("system_prompt", "You are a market analyst. Provide a concise morning briefing.")
        result = llm.generate(prompt, system_prompt=system_prompt, max_tokens=request.get("max_tokens", 512))
        return result
    except ImportError:
        raise HTTPException(status_code=503, detail="LLM not configured")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/llm/providers")
async def llm_providers():
    """List available LLM providers."""
    try:
        from services.llm import get_llm_service
        llm = get_llm_service()
        return {
            "providers": [
                {
                    "name": llm.provider,
                    "configured": bool(llm.api_key),
                }
            ]
        }
    except ImportError:
        raise HTTPException(status_code=503, detail="LLM not configured")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

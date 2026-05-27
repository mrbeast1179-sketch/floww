"""
LLM service for Confluence Decoder.

Supports multiple providers:
- Gemini (primary)
- Cerebras (fallback for fast inference)
- OpenRouter (optional)

Used for:
- Trade analysis
- Morning briefing generation
- Alert explanations
- Market commentary
"""

import os
import logging
from typing import Dict, Any
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()


_llm_service = None

def get_llm_service() -> LLMService:
    """Get the LLM service singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


async def analyze_trade_with_llm(
    ticker: str,
    spot: float,
    regime: str,
    net_gex: float,
    prediction: str,
    confidence: float,
) -> Dict[str, Any]:
    """Analyze a trade opportunity using LLM."""
    llm = get_llm_service()
    
    system_prompt = """You are an expert options trading analyst. 
Analyze the trading setup and provide a concise, actionable assessment.
Focus on: regime context, GEX implications, risk/reward, and suggested strategy.
Keep responses under 200 words."""
    
    prompt = f"""Ticker: {ticker}
Spot: ${spot:.2f}
Current Regime: {regime}
Net GEX: {net_gex:,.0f}
ML Prediction: {prediction} (confidence: {confidence:.1%})

Provide a brief trade analysis and strategy suggestion."""

    result = llm.generate(prompt, system_prompt=system_prompt, max_tokens=512)
    return result
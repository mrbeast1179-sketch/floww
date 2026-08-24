"""
LLM service for Confluence Decoder.

Supports multiple providers:
- OpenRouter (default — free models via openrouter/free router)
- Gemini (primary paid)
- Cerebras (fallback for fast inference)

Used for:
- Trade analysis
- Morning briefing generation
- Alert explanations
- Market commentary
"""

import logging
import os
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()


# ---------------------------------------------------------------------------
# Provider backends
# ---------------------------------------------------------------------------

def _call_openrouter(prompt: str, system_prompt: str, max_tokens: int, model: str) -> dict:
    """Call OpenRouter API using the openai SDK (OpenAI-compatible)."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package required: pip install openai") from None

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        extra_headers={
            "HTTP-Referer": "https://confluence-decoder.local",
            "X-Title": "Confluence Decoder",
        },
    )

    text = completion.choices[0].message.content or ""
    tokens_used = (completion.usage.total_tokens if completion.usage else 0)
    return {"text": text, "provider": "openrouter", "model": model, "tokens_used": tokens_used}


def _call_gemini(prompt: str, system_prompt: str, max_tokens: int) -> dict:
    """Call Gemini API (placeholder — requires google-generativeai)."""
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError("google-generativeai package required: pip install google-generativeai") from None

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-pro")

    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    response = model.generate_content(full_prompt, generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens))

    return {"text": response.text, "provider": "gemini", "tokens_used": 0}


# ---------------------------------------------------------------------------
# LLM Service
# ---------------------------------------------------------------------------

# Free models available on OpenRouter (no cost, good quality)
OPENROUTER_FREE_MODELS = [
    "openrouter/free",                              # auto-router for free models
    "meta-llama/llama-3.3-8b-instruct:free",
    "qwen/qwen3-8b:free",
    "google/gemma-3-1b-it:free",
    "mistralai/mistral-small-3.2-24b-instruct:free",
    "deepseek/deepseek-r1-0528:free",
]


class LLMService:
    """LLM service for trade analysis, briefings, and market commentary."""

    def __init__(self):
        self.provider = os.environ.get("LLM_PROVIDER", "openrouter").lower()
        # OpenRouter API key (primary)
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        # Gemini API key (fallback)
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "")
        # Generic LLM API key (Cerebras or others)
        self.llm_key = os.environ.get("LLM_API_KEY", "")
        # Model override for OpenRouter
        self.openrouter_model = os.environ.get("OPENROUTER_MODEL", "openrouter/free")

    @property
    def is_configured(self) -> bool:
        """Check if the current provider has a valid API key."""
        if self.provider == "openrouter":
            return bool(self.openrouter_key)
        if self.provider == "gemini":
            return bool(self.gemini_key)
        if self.provider in ("cerebras", "openrouter-cerebras"):
            return bool(self.llm_key)
        return False

    @property
    def available_providers(self) -> list[dict[str, Any]]:
        """List all providers and their configuration status."""
        return [
            {"name": "openrouter", "configured": bool(self.openrouter_key), "free": True,
             "model": self.openrouter_model},
            {"name": "gemini", "configured": bool(self.gemini_key), "free": False},
            {"name": "cerebras", "configured": bool(self.llm_key), "free": False},
        ]

    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 512) -> dict:
        """Generate a response from the configured LLM provider."""
        if self.provider == "openrouter":
            if not self.openrouter_key:
                raise ValueError("OPENROUTER_API_KEY not set — get one free at https://openrouter.ai/keys")
            return _call_openrouter(prompt, system_prompt, max_tokens, self.openrouter_model)

        if self.provider == "gemini":
            if not self.gemini_key:
                raise ValueError("GEMINI_API_KEY not set")
            return _call_gemini(prompt, system_prompt, max_tokens)

        # Fallback: try OpenRouter first, then Gemini
        if self.openrouter_key:
            return _call_openrouter(prompt, system_prompt, max_tokens, self.openrouter_model)
        if self.gemini_key:
            return _call_gemini(prompt, system_prompt, max_tokens)

        raise ValueError(f"No LLM provider configured (provider={self.provider!r}). Set OPENROUTER_API_KEY or GEMINI_API_KEY.")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """Get the LLM service singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


def reset_llm_service() -> None:
    """Reset the singleton (for testing)."""
    global _llm_service
    _llm_service = None


# ---------------------------------------------------------------------------
# Trade analysis
# ---------------------------------------------------------------------------

TRADE_ANALYST_SYSTEM = """You are an expert options trading analyst.
Analyze the trading setup and provide a concise, actionable assessment.
Focus on: regime context, GEX implications, risk/reward, and suggested strategy.
Keep responses under 200 words."""


async def analyze_trade_with_llm(
    ticker: str,
    spot: float,
    regime: str,
    net_gex: float,
    prediction: str,
    confidence: float,
) -> dict[str, Any]:
    """Analyze a trade opportunity using LLM."""
    llm = get_llm_service()

    prompt = f"""Ticker: {ticker}
Spot: ${spot:.2f}
Current Regime: {regime}
Net GEX: {net_gex:,.0f}
ML Prediction: {prediction} (confidence: {confidence:.1%})

Provide a brief trade analysis and strategy suggestion."""

    result = llm.generate(prompt, system_prompt=TRADE_ANALYST_SYSTEM, max_tokens=512)
    return result

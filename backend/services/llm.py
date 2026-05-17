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
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()


class LLMService:
    """Multi-provider LLM service."""
    
    def __init__(self):
        self.providers = {}
        self._init_providers()
    
    def _init_providers(self):
        """Initialize available LLM providers."""
        # Cerebras
        cerebras_key = os.environ.get("CEREBRAS_API_KEY")
        if cerebras_key:
            try:
                from cerebras.cloud.sdk import Cerebras
                self.providers["cerebras"] = {
                    "client": Cerebras(api_key=cerebras_key),
                    "model": "llama3.1-8b",
                    "max_tokens": 1024,
                }
                logger.info("Cerebras provider initialized")
            except Exception as e:
                logger.warning(f"Cerebras init failed: {e}")
        
        # Gemini
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=gemini_key)
                self.providers["gemini"] = {
                    "model": genai.GenerativeModel("gemini-2.0-flash"),
                    "max_tokens": 2048,
                }
                logger.info("Gemini provider initialized")
            except Exception as e:
                logger.warning(f"Gemini init failed: {e}")
        
        # OpenRouter
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if openrouter_key:
            try:
                from openai import OpenAI
                self.providers["openrouter"] = {
                    "client": OpenAI(
                        base_url="https://openrouter.ai/api/v1",
                        api_key=openrouter_key,
                    ),
                    "model": "anthropic/claude-sonnet-4",
                    "max_tokens": 2048,
                }
                logger.info("OpenRouter provider initialized")
            except Exception as e:
                logger.warning(f"OpenRouter init failed: {e}")
        
        logger.info(f"LLM providers available: {list(self.providers.keys())}")
    
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        provider: str = "cerebras",
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """Generate text from LLM."""
        
        if provider not in self.providers:
            # Fallback to first available
            if self.providers:
                provider = list(self.providers.keys())[0]
            else:
                return {"status": "error", "message": "No LLM providers available"}
        
        try:
            if provider == "cerebras":
                return self._generate_cerebras(prompt, system_prompt, max_tokens, temperature)
            elif provider == "gemini":
                return self._generate_gemini(prompt, system_prompt, max_tokens, temperature)
            elif provider == "openrouter":
                return self._generate_openrouter(prompt, system_prompt, max_tokens, temperature)
            else:
                return {"status": "error", "message": f"Unknown provider: {provider}"}
        except Exception as e:
            logger.error(f"LLM generation failed ({provider}): {e}")
            return {"status": "error", "message": str(e)}
    
    def _generate_cerebras(
        self, prompt: str, system_prompt: str, max_tokens: int, temperature: float
    ) -> Dict[str, Any]:
        """Generate using Cerebras."""
        from cerebras.cloud.sdk import Cerebras
        
        client = self.providers["cerebras"]["client"]
        model = self.providers["cerebras"]["model"]
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        completion = client.chat.completions.create(
            messages=messages,
            model=model,
            max_completion_tokens=max_tokens,
            temperature=temperature,
            top_p=1,
            stream=False,
        )
        
        return {
            "status": "ok",
            "provider": "cerebras",
            "model": model,
            "text": completion.choices[0].message.content,
        }
    
    def _generate_gemini(
        self, prompt: str, system_prompt: str, max_tokens: int, temperature: float
    ) -> Dict[str, Any]:
        """Generate using Gemini."""
        model = self.providers["gemini"]["model"]
        
        full_prompt = ""
        if system_prompt:
            full_prompt += f"{system_prompt}\n\n"
        full_prompt += prompt
        
        response = model.generate_content(
            full_prompt,
            generation_config={
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        
        return {
            "status": "ok",
            "provider": "gemini",
            "model": "gemini-2.0-flash",
            "text": response.text,
        }
    
    def _generate_openrouter(
        self, prompt: str, system_prompt: str, max_tokens: int, temperature: float
    ) -> Dict[str, Any]:
        """Generate using OpenRouter."""
        client = self.providers["openrouter"]["client"]
        model = self.providers["openrouter"]["model"]
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        
        return {
            "status": "ok",
            "provider": "openrouter",
            "model": model,
            "text": completion.choices[0].message.content,
        }


# Singleton
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
"""
turboQuantDC KV Cache Compression Service for floww backend.

Provides compressed KV cache for local HuggingFace transformer inference using
turboQuantDC's GenerationCache and TurboQuantCache. Reduces VRAM usage by 3-5x
while maintaining <0.5% attention quality loss.

Requires: pip install turboquantdc[all]

Usage:
    from services.turboquant_cache import TurboQuantService

    service = TurboQuantService()
    if service.available:
        # For HuggingFace generate() calls:
        cache = service.create_cache(preset="balanced")
        output = model.generate(inputs, past_key_values=cache, ...)

        # For streaming / generation cache:
        cache = service.create_generation_cache(preset="balanced")
        # Use with turboquantdc's generation pipeline
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# turboQuantDC is optional — gracefully degrade if not installed
HAS_TURBOQUANT = False
GenerationCache = None
TurboQuantCache = None

try:
    from turboquantdc import GenerationCache as _GenerationCache
    from turboquantdc.hf_integration import TurboQuantCache as _TurboQuantCache
    GenerationCache = _GenerationCache
    TurboQuantCache = _TurboQuantCache
    HAS_TURBOQUANT = True
except ImportError:
    logger.info("turboquantdc not installed — KV cache compression unavailable. Install: pip install turboquantdc[all]")


# Available presets (from turboquantdc's autoresearch sweep)
PRESETS = {
    "lossless": {"description": "K8/V3, FP16 window 128, anchor every 6 — near-perfect quality", "compression": "~2x"},
    "balanced": {"description": "K4/V3, FP16 window 64, anchor every 12 — best quality/speed tradeoff", "compression": "~4x"},
    "aggressive": {"description": "K3/V2, FP16 window 32, anchor every 6 — maximum compression", "compression": "~6x"},
}


class TurboQuantService:
    """Service for turboQuantDC KV cache compression in local model inference."""

    def __init__(self):
        self._available = HAS_TURBOQUANT
        self._default_preset = os.environ.get("TURBOQUANT_PRESET", "balanced")
        self._default_bits = int(os.environ.get("TURBOQUANT_KV_BITS", "4"))
        self._fp16_window = int(os.environ.get("TURBOQUANT_FP16_WINDOW", "64"))

    @property
    def available(self) -> bool:
        """Whether turboQuantDC is installed and usable."""
        return self._available

    @property
    def default_preset(self) -> str:
        return self._default_preset

    @property
    def presets(self) -> dict[str, dict[str, str]]:
        """Available quality presets."""
        return PRESETS.copy()

    def create_cache(
        self,
        preset: str | None = None,
        bits: int | None = None,
        fp16_window: int | None = None,
    ) -> Any:
        """Create a TurboQuantCache for use with HuggingFace model.generate().

        This is a drop-in replacement for HF's DynamicCache that compresses
        KV states to reduce VRAM usage by 3-5x.

        Args:
            preset: Quality preset ("lossless", "balanced", "aggressive"). Overrides bits/fp16_window.
            bits: KV cache bit width (2-8). Default: 4.
            fp16_window: Number of recent tokens to keep in FP16. Default: 64.

        Returns:
            TurboQuantCache instance (HF DynamicCache subclass).

        Raises:
            ImportError: If turboquantdc is not installed.
        """
        if not self._available:
            raise ImportError("turboquantdc not installed: pip install turboquantdc[all]")

        # Try GenerationCache.from_preset first (newer versions)
        if preset and hasattr(GenerationCache, 'from_preset'):
            return GenerationCache.from_preset(preset, fp16_window=fp16_window or self._fp16_window)

        # Use TurboQuantCache which has get_seq_length (HF cache-compatible)
        # Preset maps to bits: lossless=8, balanced=4, aggressive=3
        preset_bits = {"lossless": 8, "balanced": 4, "aggressive": 3}
        kv_bits = bits or (preset_bits.get(preset, self._default_bits) if preset else self._default_bits)
        return TurboQuantCache(bits=kv_bits)

    def create_generation_cache(
        self,
        preset: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Create a GenerationCache for turboquantdc's own generation pipeline.

        Args:
            preset: Quality preset name. If None, uses default configuration.
            **kwargs: Additional GenerationCache constructor arguments.

        Returns:
            GenerationCache instance.

        Raises:
            ImportError: If turboquantdc is not installed.
        """
        if not self._available:
            raise ImportError("turboquantdc not installed: pip install turboquantdc[all]")

        preset_cfgs = {
            "lossless": {"key_bits": 8, "val_bits": 3, "fp16_window": 128, "anchor_interval": 6},
            "balanced": {"key_bits": 4, "val_bits": 3, "fp16_window": 64, "anchor_interval": 12},
            "aggressive": {"key_bits": 3, "val_bits": 2, "fp16_window": 32, "anchor_interval": 6},
        }
        if preset:
            cfg = preset_cfgs.get(preset, preset_cfgs["balanced"]).copy()
            cfg.update(kwargs)
            return GenerationCache(**cfg)
        return GenerationCache(**kwargs)

    def get_compression_stats(self, cache: Any) -> dict[str, Any]:
        """Get compression statistics from a cache instance.

        Args:
            cache: A TurboQuantCache or GenerationCache instance.

        Returns:
            Dict with compression_ratio, method, and config details.
        """
        stats: dict[str, Any] = {
            "available": self._available,
            "preset": self._default_preset,
        }

        if not self._available:
            return stats

        try:
            if hasattr(cache, "compression_ratio"):
                stats["compression_ratio"] = cache.compression_ratio()
            if hasattr(cache, "effective_compression"):
                stats["effective_compression"] = cache.effective_compression()
            if hasattr(cache, "compressed_layer_count"):
                stats["compressed_layers"] = cache.compressed_layer_count()
            stats["method"] = "turboquantdc"
        except Exception as e:
            logger.warning(f"Failed to get compression stats: {e}")
            stats["error"] = str(e)

        return stats

    def status(self) -> dict[str, Any]:
        """Get service status and configuration."""
        return {
            "available": self._available,
            "default_preset": self._default_preset,
            "default_bits": self._default_bits,
            "fp16_window": self._fp16_window,
            "presets": PRESETS,
            "package": "turboquantdc" if self._available else None,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_turboquant_service: TurboQuantService | None = None


def get_turboquant_service() -> TurboQuantService:
    """Get the TurboQuant service singleton."""
    global _turboquant_service
    if _turboquant_service is None:
        _turboquant_service = TurboQuantService()
    return _turboquant_service


def reset_turboquant_service() -> None:
    """Reset the singleton (for testing)."""
    global _turboquant_service
    _turboquant_service = None

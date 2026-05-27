#!/usr/bin/env python3
"""
backend/services/memory/chart_embeddings.py — Chart screenshot embeddings via CLIP.

Watches ~/Documents/floww-screenshots/ for new images.
Embeds via openai/clip-vit-base-patch32.
Stores in local numpy index for fast similarity search.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path.home() / "Documents" / "floww-screenshots"
EMBEDDINGS_CACHE = Path.home() / ".hermes" / "chart_embeddings.npz"
EMBEDDINGS_META = Path.home() / ".hermes" / "chart_embeddings_meta.json"


_chart_index: Optional[ChartEmbeddingIndex] = None


def get_chart_index() -> ChartEmbeddingIndex:
    global _chart_index
    if _chart_index is None:
        _chart_index = ChartEmbeddingIndex()
    return _chart_index


def search_screenshots(text_query: str, top_k: int = 5) -> list[dict]:
    """Search screenshots by text query. Returns list of {file, filename, score}."""
    return get_chart_index().search(text_query, top_k)


def index_screenshots() -> int:
    """Index all screenshots. Returns count."""
    return get_chart_index().index_screenshots()

#!/usr/bin/env python3
"""
backend/services/memory/code_embeddings.py — Code search via embeddings.

Embeds Python/TS/JS files using sentence-transformers (CodeBERT or MiniLM fallback).
Chunks per top-level def/class + module docstring.
Stored in a local numpy index for fast cosine similarity search.
"""

import ast
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Model selection: prefer CodeBERT, fall back to MiniLM
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"  # ~90MB, fast. Use "microsoft/codebert-base" for better code understanding (~500MB)

# Directories to index
CODE_DIRS = ["backend", "frontend/src", "scripts", "qc"]
REPO_ROOT = Path(__file__).resolve().resolve().parent.parent.parent.parent

# Cache file for embeddings
EMBEDDINGS_CACHE = Path.home() / ".hermes" / "code_embeddings.npz"
EMBEDDINGS_META = Path.home() / ".hermes" / "code_embeddings_meta.json"


def extract_python_chunks(file_path: Path) -> list[CodeChunk]:
    """Extract code chunks from a Python file."""
    chunks = []
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = source.splitlines()

        # Module docstring
        if lines and (lines[0].strip().startswith('"""') or lines[0].strip().startswith("'''")):
            docstring_lines = []
            in_doc = True
            for line in lines[:20]:  # First 20 lines max
                docstring_lines.append(line)
                if line.strip().endswith('"""') or line.strip().endswith("'''"):
                    in_doc = False
                    break
            if docstring_lines:
                chunks.append(CodeChunk(
                    file_path=str(file_path),
                    line_start=1,
                    line_end=len(docstring_lines),
                    chunk_type="module_doc",
                    name=file_path.stem,
                    text="\n".join(docstring_lines),
                ))

        # AST-based extraction
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    start = node.lineno
                    end = node.end_lineno or start + 10
                    chunk_text = "\n".join(lines[start - 1:end])
                    chunks.append(CodeChunk(
                        file_path=str(file_path),
                        line_start=start,
                        line_end=end,
                        chunk_type="class" if isinstance(node, ast.ClassDef) else "function",
                        name=node.name,
                        text=chunk_text[:1000],  # Truncate long functions
                    ))
        except SyntaxError:
            pass

    except Exception as e:
        logger.warning(f"Failed to parse {file_path}: {e}")

    return chunks


def extract_js_chunks(file_path: Path) -> list[CodeChunk]:
    """Extract code chunks from JS/TS files (regex-based)."""
    chunks = []
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = source.splitlines()

        # Match function/class declarations
        func_pattern = re.compile(r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(')
        class_pattern = re.compile(r'^(?:export\s+)?class\s+(\w+)\s*(?:extends\s+\w+)?\s*\{')
        method_pattern = re.compile(r'^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{')

        for i, line in enumerate(lines, 1):
            for pattern, chunk_type in [(func_pattern, "function"), (class_pattern, "class")]:
                m = pattern.match(line)
                if m:
                    # Extract until closing brace (simplified)
                    end = min(i + 50, len(lines))
                    chunk_text = "\n".join(lines[i - 1:end])
                    chunks.append(CodeChunk(
                        file_path=str(file_path),
                        line_start=i,
                        line_end=end,
                        chunk_type=chunk_type,
                        name=m.group(1),
                        text=chunk_text[:1000],
                    ))
                    break

    except Exception as e:
        logger.warning(f"Failed to parse {file_path}: {e}")

    return chunks


_code_index: Optional[CodeEmbeddingIndex] = None


def get_code_index() -> CodeEmbeddingIndex:
    global _code_index
    if _code_index is None:
        _code_index = CodeEmbeddingIndex()
    return _code_index


def search_code(query: str, top_k: int = 5) -> list[dict]:
    """Search code by semantic similarity. Returns list of {file, line, name, score, snippet}."""
    return get_code_index().search(query, top_k)


def build_code_index() -> int:
    """Build and cache code embeddings. Returns number of chunks indexed."""
    return get_code_index().build_index()

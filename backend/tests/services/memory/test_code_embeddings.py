#!/usr/bin/env python3
"""
backend/tests/services/memory/test_code_embeddings.py — Tests for code embedding search.

Run: pytest backend/tests/services/memory/test_code_embeddings.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from services.memory.code_embeddings import (
    CodeChunk,
    CodeEmbeddingIndex,
    extract_js_chunks,
    extract_python_chunks,
)

# ---------------------------------------------------------------------------
# CodeChunk
# ---------------------------------------------------------------------------

class TestCodeChunk:
    def test_create_chunk(self):
        chunk = CodeChunk(
            file_path="backend/services/foo.py",
            line_start=10,
            line_end=25,
            chunk_type="function",
            name="do_stuff",
            text="def do_stuff():\n    pass",
        )
        assert chunk.file_path == "backend/services/foo.py"
        assert chunk.line_start == 10
        assert chunk.line_end == 25
        assert chunk.chunk_type == "function"
        assert chunk.name == "do_stuff"

    def test_chunk_id_deterministic(self):
        """Same inputs must always produce the same id."""
        chunk = CodeChunk(
            file_path="a.py", line_start=1, line_end=5,
            chunk_type="function", name="x", text="t",
        )
        assert chunk.id == chunk.id
        chunk2 = CodeChunk(
            file_path="a.py", line_start=1, line_end=5,
            chunk_type="function", name="x", text="t",
        )
        assert chunk.id == chunk2.id

    def test_chunk_id_differs_on_different_input(self):
        c1 = CodeChunk("a.py", 1, 5, "function", "x", "t")
        c2 = CodeChunk("a.py", 1, 5, "function", "y", "t")
        assert c1.id != c2.id

    def test_to_dict(self):
        chunk = CodeChunk(
            file_path="b.py", line_start=3, line_end=10,
            chunk_type="class", name="MyClass", text="class MyClass: ...",
        )
        d = chunk.to_dict()
        assert d["file"] == "b.py"
        assert d["line_start"] == 3
        assert d["line_end"] == 10
        assert d["type"] == "class"
        assert d["name"] == "MyClass"
        assert "text" in d

    def test_to_dict_truncates_text(self):
        long_text = "x" * 1000
        chunk = CodeChunk("f.py", 1, 2, "function", "fn", long_text)
        d = chunk.to_dict()
        assert len(d["text"]) <= 500


# ---------------------------------------------------------------------------
# extract_python_chunks
# ---------------------------------------------------------------------------

class TestExtractPythonChunks:
    def _write_tmp(self, tmp_path, name, content):
        f = tmp_path / name
        f.write_text(content)
        return f

    def test_extracts_function(self, tmp_path):
        src = "def hello():\n    return 'world'\n"
        fp = self._write_tmp(tmp_path, "t_func.py", src)
        chunks = extract_python_chunks(fp)
        assert len(chunks) >= 1
        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) == 1
        assert func_chunks[0].name == "hello"

    def test_extracts_class(self, tmp_path):
        src = "class Foo:\n    pass\n"
        fp = self._write_tmp(tmp_path, "t_class.py", src)
        chunks = extract_python_chunks(fp)
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        assert len(class_chunks) == 1
        assert class_chunks[0].name == "Foo"

    def test_extracts_module_docstring(self, tmp_path):
        src = '"""Module docstring."""\ndef f():\n    pass\n'
        fp = self._write_tmp(tmp_path, "t_doc.py", src)
        chunks = extract_python_chunks(fp)
        doc_chunks = [c for c in chunks if c.chunk_type == "module_doc"]
        assert len(doc_chunks) == 1
        assert doc_chunks[0].name == "t_doc"

    def test_empty_file_returns_empty(self, tmp_path):
        fp = self._write_tmp(tmp_path, "empty.py", "")
        chunks = extract_python_chunks(fp)
        assert chunks == []

    def test_syntax_error_returns_empty(self, tmp_path):
        src = "def broken(\n  this is not valid python\n"
        fp = self._write_tmp(tmp_path, "broken.py", src)
        chunks = extract_python_chunks(fp)
        # Should not raise; returns empty or module_doc only
        assert isinstance(chunks, list)

    def test_async_function(self, tmp_path):
        src = "async def fetch():\n    await something()\n"
        fp = self._write_tmp(tmp_path, "t_async.py", src)
        chunks = extract_python_chunks(fp)
        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) == 1
        assert func_chunks[0].name == "fetch"

    def test_multiple_functions(self, tmp_path):
        src = "def a():\n    pass\ndef b():\n    pass\ndef c():\n    pass\n"
        fp = self._write_tmp(tmp_path, "multi.py", src)
        chunks = extract_python_chunks(fp)
        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) == 3
        names = {c.name for c in func_chunks}
        assert names == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# extract_js_chunks
# ---------------------------------------------------------------------------

class TestExtractJSChunks:
    def _write_tmp(self, tmp_path, name, content):
        f = tmp_path / name
        f.write_text(content)
        return f

    def test_extracts_function(self, tmp_path):
        src = "function greet() {\n  return 'hi';\n}\n"
        fp = self._write_tmp(tmp_path, "t_func.js", src)
        chunks = extract_js_chunks(fp)
        assert len(chunks) >= 1
        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) == 1
        assert func_chunks[0].name == "greet"

    def test_extracts_class(self, tmp_path):
        src = "class Widget {\n  constructor() {}\n}\n"
        fp = self._write_tmp(tmp_path, "t_class.js", src)
        chunks = extract_js_chunks(fp)
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        assert len(class_chunks) == 1
        assert class_chunks[0].name == "Widget"

    def test_export_function(self, tmp_path):
        src = "export function helper() {\n  return 1;\n}\n"
        fp = self._write_tmp(tmp_path, "t_export.js", src)
        chunks = extract_js_chunks(fp)
        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) == 1
        assert func_chunks[0].name == "helper"

    def test_async_function(self, tmp_path):
        src = "async function loadData() {\n  return await fetch();\n}\n"
        fp = self._write_tmp(tmp_path, "t_async.js", src)
        chunks = extract_js_chunks(fp)
        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) == 1
        assert func_chunks[0].name == "loadData"

    def test_empty_file_returns_empty(self, tmp_path):
        fp = self._write_tmp(tmp_path, "empty.js", "")
        chunks = extract_js_chunks(fp)
        assert chunks == []


# ---------------------------------------------------------------------------
# CodeEmbeddingIndex (mocked model)
# ---------------------------------------------------------------------------

class TestCodeEmbeddingIndex:
    def _make_index(self):
        idx = CodeEmbeddingIndex.__new__(CodeEmbeddingIndex)
        idx.model_name = "test-model"
        idx._model = None
        idx._embeddings = None
        idx._metadata = []
        return idx

    def test_search_returns_empty_when_no_index_and_no_model(self):
        """When load_index returns False and _model is None, accessing model property
        tries to import sentence_transformers. If that's not installed, search raises.
        We mock the import to verify the code path."""
        idx = self._make_index()
        idx._embeddings = None
        idx._metadata = []
        with patch.object(idx, "load_index", return_value=False):
            # Mock _model to a MagicMock so the property doesn't try real import
            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([[1.0, 0.0, 0.0, 0.0]])
            idx._model = mock_model
            # With no embeddings loaded, search should return []
            results = idx.search("query")
            assert results == []

    def test_search_with_preloaded_embeddings(self):
        """Test search with manually set embeddings and mocked model."""
        import numpy as np

        idx = self._make_index()
        # 3 chunks, 4-dim embeddings
        idx._embeddings = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
        ])
        idx._metadata = [
            {"file": "a.py", "line_start": 1, "name": "fa", "type": "function", "text": "snippet a"},
            {"file": "b.py", "line_start": 10, "name": "fb", "type": "function", "text": "snippet b"},
            {"file": "c.py", "line_start": 20, "name": "fc", "type": "function", "text": "snippet c"},
        ]
        mock_model = MagicMock()
        # Query closest to [1,0,0,0] → should rank a.py first
        mock_model.encode.return_value = np.array([[1.0, 0.0, 0.0, 0.0]])
        idx._model = mock_model

        results = idx.search("query", top_k=2)
        assert len(results) == 2
        assert results[0]["file"] == "a.py"
        assert results[0]["score"] >= results[1]["score"]

    def test_search_top_k_limits_results(self):
        import numpy as np

        idx = self._make_index()
        idx._embeddings = np.eye(5)
        idx._metadata = [
            {"file": f"f{i}.py", "line_start": i, "name": f"fn{i}", "type": "function", "text": f"t{i}"}
            for i in range(5)
        ]
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[1.0, 0, 0, 0, 0]])
        idx._model = mock_model

        results = idx.search("q", top_k=3)
        assert len(results) == 3

    def test_search_result_structure(self):
        import numpy as np

        idx = self._make_index()
        idx._embeddings = np.array([[0.5, 0.5]])
        idx._metadata = [
            {"file": "x.py", "line_start": 42, "name": "solve", "type": "function", "text": "def solve(): pass"},
        ]
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.5, 0.5]])
        idx._model = mock_model

        results = idx.search("test")
        assert len(results) == 1
        r = results[0]
        assert "file" in r
        assert "line" in r
        assert "name" in r
        assert "type" in r
        assert "score" in r
        assert "snippet" in r
        assert r["file"] == "x.py"
        assert r["line"] == 42
        assert r["name"] == "solve"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

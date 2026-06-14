#!/usr/bin/env python3
"""
backend/tests/services/memory/test_code_embeddings.py - Tests for code embedding search.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from services.memory.code_embeddings import (  # noqa: E402, I001
    CodeChunk,
    CodeEmbeddingIndex,
    extract_js_chunks,
    extract_python_chunks,
)


class TestCodeChunk:
    def test_create_chunk(self):
        chunk = CodeChunk("backend/services/foo.py", 10, 25, "function", "do_stuff",
                          "def do_stuff():\n    pass")
        assert chunk.file_path == "backend/services/foo.py"
        assert chunk.line_start == 10
        assert chunk.chunk_type == "function"
        assert chunk.name == "do_stuff"

    def test_chunk_id_deterministic(self):
        c1 = CodeChunk("a.py", 1, 5, "function", "x", "t")
        c2 = CodeChunk("a.py", 1, 5, "function", "x", "t")
        assert c1.id == c2.id

    def test_chunk_id_differs(self):
        c1 = CodeChunk("a.py", 1, 5, "function", "x", "t")
        c2 = CodeChunk("a.py", 1, 5, "function", "y", "t")
        assert c1.id != c2.id

    def test_to_dict(self):
        chunk = CodeChunk("b.py", 3, 10, "class", "MyClass", "class MyClass: ...")
        d = chunk.to_dict()
        assert d["file"] == "b.py"
        assert d["type"] == "class"
        assert d["name"] == "MyClass"
        assert "text" in d

    def test_to_dict_truncates(self):
        chunk = CodeChunk("f.py", 1, 2, "function", "fn", "x" * 1000)
        assert len(chunk.to_dict()["text"]) <= 500


class TestExtractPythonChunks:
    def _write(self, tmp_path, name, content):
        f = tmp_path / name
        f.write_text(content)
        return f

    def test_function(self, tmp_path):
        fp = self._write(tmp_path, "t.py", "def hello():\n    return 'world'\n")
        chunks = extract_python_chunks(fp)
        funcs = [c for c in chunks if c.chunk_type == "function"]
        assert len(funcs) == 1 and funcs[0].name == "hello"

    def test_class(self, tmp_path):
        fp = self._write(tmp_path, "t.py", "class Foo:\n    pass\n")
        chunks = extract_python_chunks(fp)
        classes = [c for c in chunks if c.chunk_type == "class"]
        assert len(classes) == 1 and classes[0].name == "Foo"

    def test_docstring(self, tmp_path):
        fp = self._write(tmp_path, "t.py", '"""Doc."""\ndef f():\n    pass\n')
        docs = [c for c in extract_python_chunks(fp) if c.chunk_type == "module_doc"]
        assert len(docs) == 1

    def test_empty(self, tmp_path):
        fp = self._write(tmp_path, "t.py", "")
        assert extract_python_chunks(fp) == []

    def test_syntax_error(self, tmp_path):
        fp = self._write(tmp_path, "t.py", "def broken(\n")
        assert isinstance(extract_python_chunks(fp), list)

    def test_async(self, tmp_path):
        fp = self._write(tmp_path, "t.py", "async def fetch():\n    pass\n")
        funcs = [c for c in extract_python_chunks(fp) if c.chunk_type == "function"]
        assert len(funcs) == 1 and funcs[0].name == "fetch"

    def test_multiple(self, tmp_path):
        fp = self._write(tmp_path, "t.py", "def a():\n    pass\ndef b():\n    pass\n")
        funcs = [c for c in extract_python_chunks(fp) if c.chunk_type == "function"]
        assert len(funcs) == 2


class TestExtractJSChunks:
    def _write(self, tmp_path, name, content):
        f = tmp_path / name
        f.write_text(content)
        return f

    def test_function(self, tmp_path):
        fp = self._write(tmp_path, "t.js", "function greet() {\n}\n")
        funcs = [c for c in extract_js_chunks(fp) if c.chunk_type == "function"]
        assert len(funcs) == 1 and funcs[0].name == "greet"

    def test_class(self, tmp_path):
        fp = self._write(tmp_path, "t.js", "class Widget {\n}\n")
        classes = [c for c in extract_js_chunks(fp) if c.chunk_type == "class"]
        assert len(classes) == 1 and classes[0].name == "Widget"

    def test_export(self, tmp_path):
        fp = self._write(tmp_path, "t.js", "export function helper() {\n}\n")
        funcs = [c for c in extract_js_chunks(fp) if c.chunk_type == "function"]
        assert len(funcs) == 1 and funcs[0].name == "helper"

    def test_async(self, tmp_path):
        fp = self._write(tmp_path, "t.js", "async function load() {\n}\n")
        funcs = [c for c in extract_js_chunks(fp) if c.chunk_type == "function"]
        assert len(funcs) == 1 and funcs[0].name == "load"

    def test_empty(self, tmp_path):
        fp = self._write(tmp_path, "t.js", "")
        assert extract_js_chunks(fp) == []


class TestCodeEmbeddingIndex:
    def _make(self):
        idx = CodeEmbeddingIndex.__new__(CodeEmbeddingIndex)
        idx.model_name = "test"
        idx._model = None
        idx._embeddings = None
        idx._metadata = []
        return idx

    def test_search_empty_no_index(self):
        idx = self._make()
        idx._embeddings = None
        with patch.object(idx, "load_index", return_value=False):
            idx._model = MagicMock()
            idx._model.encode.return_value = np.array([[1.0, 0.0]])
            assert idx.search("q") == []

    def test_search_with_embeddings(self):
        idx = self._make()
        idx._embeddings = np.array([[1.0, 0.0], [0.0, 1.0]])
        idx._metadata = [
            {"file": "a.py", "line_start": 1, "name": "fa", "type": "function", "text": "t"},
            {"file": "b.py", "line_start": 10, "name": "fb", "type": "function", "text": "t"},
        ]
        mock = MagicMock()
        mock.encode.return_value = np.array([[1.0, 0.0]])
        idx._model = mock
        results = idx.search("q", top_k=1)
        assert len(results) == 1 and results[0]["file"] == "a.py"

    def test_search_top_k(self):
        idx = self._make()
        idx._embeddings = np.eye(5)
        idx._metadata = [
            {"file": f"f{i}.py", "line_start": i, "name": f"fn{i}", "type": "function", "text": "t"}
            for i in range(5)
        ]
        mock = MagicMock()
        mock.encode.return_value = np.array([[1.0, 0, 0, 0, 0]])
        idx._model = mock
        assert len(idx.search("q", top_k=3)) == 3

    def test_search_result_fields(self):
        idx = self._make()
        idx._embeddings = np.array([[0.5, 0.5]])
        idx._metadata = [
            {"file": "x.py", "line_start": 42, "name": "solve", "type": "function", "text": "def solve(): pass"},
        ]
        mock = MagicMock()
        mock.encode.return_value = np.array([[0.5, 0.5]])
        idx._model = mock
        r = idx.search("t")[0]
        for field in ("file", "line", "name", "type", "score", "snippet"):
            assert field in r


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

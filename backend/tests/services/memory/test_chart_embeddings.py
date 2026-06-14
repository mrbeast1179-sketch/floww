#!/usr/bin/env python3
"""
backend/tests/services/memory/test_chart_embeddings.py - Tests for chart screenshot embeddings.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

_mock_pil = types.ModuleType("PIL")
_mock_img = types.ModuleType("PIL.Image")
_mock_img.open = MagicMock()
_mock_pil.Image = _mock_img
sys.modules["PIL"] = _mock_pil
sys.modules["PIL.Image"] = _mock_img
_mock_clip = types.ModuleType("clip")
_mock_clip.load = MagicMock(return_value=(MagicMock(), MagicMock()))
_mock_clip.tokenize = MagicMock(return_value=MagicMock())
sys.modules["clip"] = _mock_clip

from services.memory.chart_embeddings import (  # noqa: E402
    ChartEmbeddingIndex,
    get_chart_index,
    index_screenshots,
    search_screenshots,
)


def _mock_tensor(arr):
    t = MagicMock()
    t.cpu.return_value = t
    t.numpy.return_value = arr
    t.flatten.return_value = arr.flatten()
    return t


class TestChartEmbeddingIndex:
    def _make(self):
        idx = ChartEmbeddingIndex.__new__(ChartEmbeddingIndex)
        idx.model_name = "ViT-B/32"
        idx._model = None
        idx._preprocess = None
        idx._embeddings = None
        idx._metadata = []
        return idx

    def _mock_model(self, arr):
        m = MagicMock()
        m.encode_text.return_value = _mock_tensor(arr)
        return m

    def test_load_index_missing(self, tmp_path):
        idx = self._make()
        with patch("services.memory.chart_embeddings.EMBEDDINGS_CACHE", tmp_path / "n.npz"), \
             patch("services.memory.chart_embeddings.EMBEDDINGS_META", tmp_path / "n.json"):
            assert idx.load_index() is False

    def test_load_index_present(self, tmp_path):
        idx = self._make()
        cache = tmp_path / "c.npz"
        meta = tmp_path / "c.json"
        np.savez_compressed(cache, embeddings=np.eye(3))
        meta.write_text('[{"file": "/a.png", "filename": "a.png"}]')
        with patch("services.memory.chart_embeddings.EMBEDDINGS_CACHE", cache), \
             patch("services.memory.chart_embeddings.EMBEDDINGS_META", meta):
            assert idx.load_index() is True
            assert idx._embeddings.shape == (3, 3)

    def test_search_results(self):
        idx = self._make()
        idx._embeddings = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        idx._metadata = [
            {"file": "/a.png", "filename": "a.png"},
            {"file": "/b.png", "filename": "b.png"},
            {"file": "/c.png", "filename": "c.png"},
        ]
        idx._model = self._mock_model(np.array([[1.0, 0.0, 0.0]]))
        r = idx.search("q", top_k=2)
        assert len(r) == 2 and r[0]["filename"] == "a.png"

    def test_search_structure(self):
        idx = self._make()
        idx._embeddings = np.array([[0.5, 0.5]])
        idx._metadata = [{"file": "/p.png", "filename": "p.png"}]
        idx._model = self._mock_model(np.array([[0.5, 0.5]]))
        r = idx.search("q")[0]
        assert all(k in r for k in ("file", "filename", "score"))

    def test_search_top_k(self):
        idx = self._make()
        idx._embeddings = np.eye(5)
        idx._metadata = [{"file": f"/{i}.png", "filename": f"{i}.png"} for i in range(5)]
        idx._model = self._mock_model(np.array([[1.0, 0, 0, 0, 0]]))
        assert len(idx.search("q", top_k=3)) == 3

    def test_search_empty(self):
        idx = self._make()
        idx._embeddings = None
        with patch.object(idx, "load_index", return_value=False):
            assert idx.search("q") == []

    def test_search_scores_floats(self):
        idx = self._make()
        idx._embeddings = np.array([[1.0, 0.0], [0.0, 1.0]])
        idx._metadata = [{"file": "/a.png", "filename": "a.png"}, {"file": "/b.png", "filename": "b.png"}]
        idx._model = self._mock_model(np.array([[0.7, 0.7]]))
        for r in idx.search("q"):
            assert isinstance(r["score"], float)

    def test_search_zero_norm(self):
        idx = self._make()
        idx._embeddings = np.array([[0.0, 0.0], [1.0, 0.0]])
        idx._metadata = [{"file": "/z.png", "filename": "z.png"}, {"file": "/n.png", "filename": "n.png"}]
        idx._model = self._mock_model(np.array([[1.0, 0.0]]))
        assert len(idx.search("q")) == 2

    def test_index_dir_missing(self, tmp_path):
        assert self._make().index_screenshots(tmp_path / "ne") == 0

    def test_index_no_images(self, tmp_path):
        (tmp_path / "r.txt").write_text("x")
        assert self._make().index_screenshots(tmp_path) == 0


class TestModuleFunctions:
    def test_singleton(self):
        from services.memory import chart_embeddings as m
        m._chart_index = None
        assert get_chart_index() is get_chart_index()
        m._chart_index = None

    def test_search_delegates(self):
        with patch("services.memory.chart_embeddings.get_chart_index") as g:
            mi = MagicMock()
            mi.search.return_value = [{"file": "/a.png", "filename": "a.png", "score": 0.9}]
            g.return_value = mi
            r = search_screenshots("q", top_k=3)
            mi.search.assert_called_once_with("q", 3)
            assert len(r) == 1

    def test_index_delegates(self):
        with patch("services.memory.chart_embeddings.get_chart_index") as g:
            mi = MagicMock()
            mi.index_screenshots.return_value = 7
            g.return_value = mi
            assert index_screenshots() == 7


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

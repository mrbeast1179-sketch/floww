#!/usr/bin/env python3
"""
backend/tests/services/memory/test_voice_embeddings.py - Tests for voice memo config/constants.
"""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from services.memory import voice_embeddings as ve


class TestVoiceMemosDir:
    def test_contains_voice_memos(self):
        assert isinstance(ve.VOICE_MEMOS_DIR, Path)
        assert "voice" in str(ve.VOICE_MEMOS_DIR).lower()

    def test_under_home(self):
        assert str(ve.VOICE_MEMOS_DIR).startswith(str(Path.home()))

    def test_env_override(self, monkeypatch):
        p = Path("/tmp/custom-voice")
        monkeypatch.setenv("VOICE_MEMOS_DIR", str(p))
        importlib.reload(ve)
        assert p == ve.VOICE_MEMOS_DIR

    def test_nonexistent_ok(self):
        p = Path("/no/such/dir")
        with patch.dict(os.environ, {"VOICE_MEMOS_DIR": str(p)}):
            importlib.reload(ve)
            assert p == ve.VOICE_MEMOS_DIR


class TestProcessedState:
    def test_is_path(self):
        assert isinstance(ve.PROCESSED_STATE, Path)

    def test_under_hermes(self):
        assert ".hermes" in str(ve.PROCESSED_STATE)

    def test_json_ext(self):
        assert ve.PROCESSED_STATE.suffix == ".json"


class TestModuleAttributes:
    def test_exports(self):
        assert hasattr(ve, "VOICE_MEMOS_DIR")
        assert hasattr(ve, "PROCESSED_STATE")

    def test_no_functions(self):
        import inspect
        fns = [n for n, o in inspect.getmembers(ve)
               if inspect.isfunction(o) and not n.startswith("_")]
        assert fns == [], f"Unexpected: {fns}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

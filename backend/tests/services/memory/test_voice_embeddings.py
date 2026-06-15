#!/usr/bin/env python3
"""
backend/tests/services/memory/test_voice_embeddings.py — Tests for voice memo config/constants.

voice_embeddings.py is a constants/config module: VOICE_MEMOS_DIR, PROCESSED_STATE.
The actual transcription logic depends on whisper which is heavy;
this test covers the module-level path construction and env-var override.

Run: pytest backend/tests/services/memory/test_voice_embeddings.py -v
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from services.memory import voice_embeddings as ve


class TestVoiceMemosDir:
    def test_default_path_contains_voice_memos(self):
        d = ve.VOICE_MEMOS_DIR
        assert isinstance(d, Path)
        assert "Voice Memos" in str(d) or "VoiceMemos" in str(d) or "voice" in str(d).lower()

    def test_default_path_under_home(self):
        home = Path.home()
        # The default path should be under home directory
        assert str(ve.VOICE_MEMOS_DIR).startswith(str(home))

    def test_env_var_override(self, monkeypatch):
        """VOICE_MEMOS_DIR env var should override the default."""
        custom = Path("/tmp/custom-voice-dir")
        monkeypatch.setenv("VOICE_MEMOS_DIR", str(custom))
        # Re-evaluate the module-level variable by reimporting
        import importlib
        import services.memory.voice_embeddings as ve_reloaded
        importlib.reload(ve_reloaded)
        assert ve_reloaded.VOICE_MEMOS_DIR == custom

    def test_env_var_raises_no_error_if_dir_missing(self):
        """VOICE_MEMOS_DIR can point to a nonexistent dir; it's just a path."""
        custom = Path("/nonexistent/voice/memos/path")
        with patch.dict(os.environ, {"VOICE_MEMOS_DIR": str(custom)}):
            import importlib
            import services.memory.voice_embeddings as ve2
            importlib.reload(ve2)
            assert ve2.VOICE_MEMOS_DIR == custom


class TestProcessedState:
    def test_processed_state_is_path(self):
        assert isinstance(ve.PROCESSED_STATE, Path)

    def test_processed_state_under_hermes_dir(self):
        """State file should be under ~/.hermes/"""
        home = Path.home()
        assert str(ve.PROCESSED_STATE).startswith(str(home / ".hermes"))
        assert "voice_memos_processed.json" in str(ve.PROCESSED_STATE)

    def test_processed_state_has_json_extension(self):
        assert ve.PROCESSED_STATE.suffix == ".json"


class TestModuleAttributes:
    def test_module_has_expected_exports(self):
        """Module exposes VOICE_MEMOS_DIR and PROCESSED_STATE."""
        assert hasattr(ve, "VOICE_MEMOS_DIR")
        assert hasattr(ve, "PROCESSED_STATE")

    def test_no_transcribe_function_yet(self):
        """voice_embeddings.py currently has no function definitions (constants only)."""
        # If someday a transcribe function is added, this test documents current state
        import inspect
        members = [name for name, obj in inspect.getmembers(ve) if inspect.isfunction(obj) and not name.startswith("_")]
        # Currently should be empty; if functions are added, update this test
        assert members == [], f"Unexpected functions found: {members}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

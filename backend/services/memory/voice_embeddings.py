#!/usr/bin/env python3
"""
backend/services/memory/voice_embeddings.py — Voice memo transcription via Whisper.

Watches iOS Voice Memos sync folder for new .m4a files.
Transcribes via whisper-base (local model, ~150MB).
Inserts transcript into mem0 with tags [source:voice_memo, audio].
"""

import json
import logging
import hashlib
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# iOS Voice Memos iCloud sync path (configurable via env var)
VOICE_MEMOS_DIR = Path(os.environ.get(
    "VOICE_MEMOS_DIR",
    str(Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "Voice Memos")
))

# State file to track processed memos
PROCESSED_STATE = Path.home() / ".hermes" / "voice_memos_processed.json"


def load_processed() -> dict:
    if PROCESSED_STATE.exists():
        return json.loads(PROCESSED_STATE.read_text())
    return {}


def save_processed(state: dict):
    PROCESSED_STATE.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_STATE.write_text(json.dumps(state))


def find_new_memos(voice_dir: Path = VOICE_MEMOS_DIR) -> list[Path]:
    """Find new voice memo files that haven't been processed."""
    if not voice_dir.exists():
        logger.info(f"Voice memos dir not found: {voice_dir}")
        return []

    processed = load_processed()
    new_files = []

    for ext in ("*.m4a", "*.mp3", "*.wav", "*.aac"):
        for f in voice_dir.rglob(ext):
            file_hash = hashlib.md5(f.read_bytes()[:4096]).hexdigest()
            if str(f) not in processed:
                new_files.append(f)

    return new_files


def transcribe_memo(file_path: Path, model_size: str = "base") -> Optional[str]:
    """Transcribe a voice memo using Whisper."""
    try:
        import whisper
        model = whisper.load_model(model_size)
        result = model.transcribe(str(file_path), language="en")
        return result.get("text", "").strip()
    except ImportError:
        logger.error("whisper not installed. Run: pip install openai-whisper")
        return None
    except Exception as e:
        logger.error(f"Transcription failed for {file_path}: {e}")
        return None


def process_voice_memos(mem0_client, user_id: str = "user_c778280e23af",
                        voice_dir: Path = VOICE_MEMOS_DIR) -> int:
    """Process all new voice memos. Returns count of new transcripts added."""
    new_files = find_new_memos(voice_dir)
    if not new_files:
        logger.info("No new voice memos to process")
        return 0

    processed = load_processed()
    added = 0

    for memo_file in new_files:
        logger.info(f"Transcribing: {memo_file.name}")
        transcript = transcribe_memo(memo_file)

        if transcript:
            # Insert into mem0
            mem0_client.add(
                messages=[{"role": "user", "content": transcript}],
                user_id=user_id,
                metadata={
                    "source": "voice_memo",
                    "audio_file": str(memo_file),
                    "audio_filename": memo_file.name,
                    "transcribed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            added += 1

        # Mark as processed
        file_hash = hashlib.md5(memo_file.read_bytes()[:4096]).hexdigest()
        processed[str(memo_file)] = {
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "transcript": transcript[:200] if transcript else None,
        }

    save_processed(processed)
    logger.info(f"Processed {added}/{len(new_files)} voice memos")
    return added


# Import at bottom to avoid circular imports
from datetime import datetime, timezone
import os

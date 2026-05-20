#!/usr/bin/env python3
"""
scripts/install_ask_hermes.py — Install ask-hermes as a shell command.

Usage:
  python3 scripts/install_ask_hermes.py

This creates a symlink at /usr/local/bin/ask-hermes pointing to scripts/ask_hermes.py.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "ask_hermes.py"
BIN_PATH = Path("/usr/local/bin/ask-hermes")

def main():
    # Make script executable
    SCRIPT_PATH.chmod(0o755)

    # Create symlink
    if BIN_PATH.exists() or BIN_PATH.is_symlink():
        BIN_PATH.unlink()

    try:
        BIN_PATH.symlink_to(SCRIPT_PATH)
        print(f"Installed: {BIN_PATH} -> {SCRIPT_PATH}")
        print("Usage: ask-hermes \"your query here\"")
    except PermissionError:
        print(f"Permission denied. Run with sudo:")
        print(f"  sudo ln -sf {SCRIPT_PATH} {BIN_PATH}")
        sys.exit(1)

if __name__ == "__main__":
    main()

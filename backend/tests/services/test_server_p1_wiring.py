"""
backend/tests/services/test_server_p1_wiring.py

Pinned regression tests for the P1 wiring fixes in backend/server.py.
These are SOURCE-TEXT invariants (do NOT import server — importing triggers
heavy startup work including Motor client init).

Pinned properties:

P1 entry #3 — `server.py: MONGO_URL hard-read`.
- Source must NOT contain `MONGO_URL = os.environ["MONGO_URL"]` (KeyError on
  start-up when env is unset).
- Source MUST read MONGO_URL via `os.getenv("MONGO_URL", <default>)` with at
  least one default-on-miss fallback so import succeeds without env set.

P1 entry #4 — `server.py: replay_router duplicate registration`.
- Source MUST contain the `from routes.replay import router as replay_router`
  import statement exactly ONCE (not twice).
- Source MUST contain the `app.include_router(replay_router, ...)` call exactly
  ONCE (not twice).  Pre-fix had lines 2905+2907 and 3092+3094 both registering
  the same router — the duplicate is harmless functionally but pollutes route
  ordering and Pythons-include-twice warnings in newer FastAPI/Starlette
  versions.

See docs/superpowers/plans/2026-06-20-freebuff-decoder-hardening-60h.md.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from ._subprocess_helpers import _SUBPROCESS_MIN_ENV

SERVER_PY = Path(__file__).resolve().parents[2] / "server.py"


def _read_server_source() -> str:
    return SERVER_PY.read_text(encoding="utf-8")


class TestMongoUrlEnvDefault:
    """Pinned regression: server.py must NOT hard-read MONGO_URL via os.environ[..]."""

    def test_source_does_not_hard_read_mongo_url(self):
        source = _read_server_source()
        # Match `MONGO_URL = os.environ["MONGO_URL"]` (any whitespace tolerated).
        hard_read = re.findall(
            r'MONGO_URL\s*=\s*os\.environ\s*\[\s*["\']MONGO_URL["\']\s*\]',
            source,
        )
        assert hard_read == [], (
            f"server.py hard-reads MONGO_URL (KeyError on import when env unset): "
            f"found {len(hard_read)} occurrence(s) — replace with "
            f'`os.getenv("MONGO_URL", "mongodb://localhost:27017")` '
            f"(see docs/superpowers/plans/2026-06-20-freebuff-decoder-hardening-60h.md)"
        )

    def test_source_uses_getenv_with_default_for_mongo_url(self):
        source = _read_server_source()
        # Must read via os.getenv with at least one default-on-miss.
        # Pattern allows whitespace plus docstring-or-explanatory-comment-chains.
        getenv = re.findall(
            r'MONGO_URL\s*=\s*os\.getenv\s*\(\s*["\']MONGO_URL["\']\s*,',
            source,
        )
        assert getenv, (
            "server.py does not use os.getenv with default for MONGO_URL — "
            "degraded start-up robustness (see Freebuff Handoff non-negotiables)"
        )


class TestReplayRouterDedupe:
    """Pinned regression: replay_router must be imported + registered exactly once."""

    def test_replay_router_imported_exactly_once(self):
        source = _read_server_source()
        imports = re.findall(
            r"^\s*from\s+routes\.replay\s+import\s+router\s+as\s+replay_router\s*$",
            source,
            re.MULTILINE,
        )
        assert len(imports) == 1, (
            f"server.py imports `from routes.replay import router as replay_router` "
            f"{len(imports)} times — must be exactly 1 (pre-fix was 2: lines 2905+3092). "
            f"Delete the duplicate block at the second occurrence."
        )

    def test_replay_router_include_exactly_once(self):
        source = _read_server_source()
        includes = re.findall(
            r"^\s*app\.include_router\s*\(\s*replay_router\b",
            source,
            re.MULTILINE,
        )
        assert len(includes) == 1, (
            f"server.py calls `app.include_router(replay_router, ...)` "
            f"{len(includes)} times — must be exactly 1 (pre-fix was 2: lines 2907+3094). "
            f"Delete the duplicate include-router call."
        )


class TestServerP1ImportDoesNotCrash:
    """Behavioural regression: import server.py with MONGO_URL unset must succeed
    (uses localhost default).  Runs in a subprocess so server.py's module-level
    side effects (Motor init, router registration) do not pollute this test session."""

    def test_server_module_imports_successfully_with_mongo_url_unset(self):
        import subprocess

        repo_root = Path(__file__).resolve().parents[3]
        backend_dir = repo_root / "backend"

        env = {
            **_SUBPROCESS_MIN_ENV,
            "PYTHONPATH": str(backend_dir),
            "HOME": str(Path.home()),
        }
        # Intentionally do NOT set MONGO_URL: the test exercises the default-on-miss.

        result = subprocess.run(
            [sys.executable, "-W", "ignore", "-c",
             "import os; assert 'MONGO_URL' not in os.environ, 'env leak'; "
             "import server; "
             "assert hasattr(server, 'MONGO_URL'), 'MONGO_URL not on server module'; "
             "print('MONGO_URL=', server.MONGO_URL)"],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            cwd=str(backend_dir),
        )
        assert result.returncode == 0, (
            "server.py failed to import with MONGO_URL env unset — hard-read "
            f"still present?\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
        # Default fallback URL should mention localhost (or 127.0.0.1) and standard mongodb port.
        assert ("mongodb://localhost" in result.stdout
                or "mongodb://127.0.0.1" in result.stdout), (
            f"server.MONGO_URL did not fall back to a localhost default when env unset: "
            f"{result.stdout!r}"
        )

"""
Steal-Three Dev Sidecar (:8001)
================================

Thin launcher that mounts the consolidated ``steal_three_router`` from
``backend/routes/steal_three.py`` on a standalone FastAPI app, so that
:class routes work identically on :8000 (via ``backend/server.py``) and
on :8001 (via this file). Only the sidecar-specific concerns live here:

  * CORSMiddleware allowlist (dev convenience — main :8000 already has
    its own CORSMiddleware configured elsewhere in ``server.py``).
  * The ``/health`` probe (``server.py`` already exposes ``/`` and ``/api/``
    health probes, so we deliberately don't mount one via the router).
  * The ``uvicorn.run`` launcher when called as ``__main__``.

Endpoints:

  GET /api/dual_gex/{ticker}             — rank #1 Dual-GEX + activity ratio
  GET /api/iv_mid/{ticker}?width=N        — rank #5 IV-from-mid cross-check
  GET /api/screener/income?symbol=...     — rank #3 Wheel income screener
  GET /health                            — sidecar-only dev probe

Run locally:

    cd backend && python -m services.steal_three_server

Override the port with ``STEAL_THREE_PORT=…``.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Canonical API surface — same router that backend/server.py serves on :8000.
from routes.steal_three import router as steal_three_router

log = logging.getLogger("steal_three")
log.setLevel(logging.INFO)
if not log.handlers:
    log.addHandler(logging.StreamHandler())


app = FastAPI(
    title="floww steal-three sidecar",
    version="0.2.0",
    description=(
        "Standalone :8001 copy of the consolidated steal-three router. The same "
        "endpoints live on the canonical floww backend (:8000) via the include "
        "in backend/server.py — this sidecar exists for offline dev / quick "
        "iteration when the main process is being edited by another chat."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


# Sidecar-only — server.py has its own root-level health probes, so we keep
# this out of the consolidated router.
@app.get("/health")
def _sidecar_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "steal-three-sidecar",
        "ts": datetime.now(UTC).isoformat(),
    }


# Same Router that backend/server.py includes on :8000.
app.include_router(steal_three_router)


if __name__ == "__main__":
    port = int(os.environ.get("STEAL_THREE_PORT", "8001"))
    log.info("Starting steal-three sidecar on :%d (CORS allow http://localhost:3000)", port)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")

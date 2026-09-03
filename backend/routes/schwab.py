"""
backend/routes/schwab.py

Schwab integration — RETIRED 2026-09-03 (public-api-only policy).

floww has no Schwab account and per architect directive uses only the
Public.com API. Every route returns HTTP 410 Gone with a `replacement`
pointer to the /api/public/brokerage/* equivalent. The module is kept so
imports and router mounting don't break.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

_RETIRED = (
    "Schwab retired 2026-09-03 — floww is public-API-only. "
    "Use the replacement /api/public/brokerage/* endpoint."
)


def _gone(replacement: str) -> JSONResponse:
    return JSONResponse(
        status_code=410,
        content={"error": "schwab_retired", "message": _RETIRED, "replacement": replacement},
    )


@router.get("/schwab/auth-url")
async def schwab_auth_url():
    return _gone("/api/public/brokerage/account")


@router.post("/schwab/auth")
async def schwab_auth(request: dict):
    return _gone("/api/public/brokerage/account")


@router.get("/schwab/accounts")
async def schwab_accounts():
    return _gone("/api/public/brokerage/account")


@router.get("/schwab/positions/{account_hash}")
async def schwab_positions(account_hash: str):
    return _gone("/api/public/brokerage/portfolio")


@router.get("/schwab/sweeps/{account_hash}")
async def schwab_sweeps(account_hash: str):
    return _gone("/api/public/chain/SPY")


@router.post("/schwab/import-to-portfolio/{name}/{account_hash}")
async def schwab_import(name: str, account_hash: str):
    return _gone("/api/public/brokerage/portfolio")

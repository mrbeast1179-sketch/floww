"""
backend/routes/schwab.py

Schwab integration routes.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/schwab/auth-url")
async def schwab_auth_url():
    from server import get_schwab_auth_url
    return get_schwab_auth_url()


@router.post("/schwab/auth")
async def schwab_auth(request: dict):
    from server import schwab_auth_handler
    result = await schwab_auth_handler(request)
    return result


@router.get("/schwab/accounts")
async def schwab_accounts():
    from server import schwab_get_accounts
    result = await schwab_get_accounts()
    return result


@router.get("/schwab/positions/{account_hash}")
async def schwab_positions(account_hash: str):
    from server import schwab_get_positions
    result = await schwab_get_positions(account_hash)
    return result


@router.get("/schwab/sweeps/{account_hash}")
async def schwab_sweeps(account_hash: str):
    from server import schwab_get_sweeps
    result = await schwab_get_sweeps(account_hash)
    return result


@router.post("/schwab/import-to-portfolio/{name}/{account_hash}")
async def schwab_import(name: str, account_hash: str):
    from server import schwab_import_to_portfolio
    result = await schwab_import_to_portfolio(name, account_hash)
    return result

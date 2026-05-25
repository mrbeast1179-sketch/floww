"""
backend/routes/nexus.py

Social trading scaffold — leaderboard, comments, waitlist.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nexus", tags=["nexus"])

# Scaffold data — empty until backend is implemented
_leaderboard: List[Dict] = []
_comments: List[Dict] = []
_waitlist: List[Dict] = []


@router.get("/leaderboard")
async def get_leaderboard():
    """Get the social trading leaderboard."""
    return {"leaderboard": _leaderboard, "status": "beta"}


@router.get("/comments")
async def get_comments(ticker: str = None):
    """Get comment thread. Optionally filtered by ticker."""
    comments = _comments
    if ticker:
        comments = [c for c in comments if c.get("ticker", "").upper() == ticker.upper()]
    return {"comments": comments}


@router.post("/comments")
async def post_comment(comment: Dict[str, Any]):
    """Post a new comment (scaffold — no auth yet)."""
    comment["id"] = len(_comments) + 1
    _comments.append(comment)
    return {"status": "posted", "id": comment["id"]}


@router.post("/waitlist")
async def join_waitlist(entry: Dict[str, Any]):
    """Join the Nexus private beta waitlist."""
    entry["id"] = len(_waitlist) + 1
    _waitlist.append(entry)
    return {"status": "waitlisted", "id": entry["id"]}


@router.get("/status")
async def nexus_status():
    """Get Nexus status."""
    return {
        "status": "private_beta",
        "leaderboard_entries": len(_leaderboard),
        "comments": len(_comments),
        "waitlist": len(_waitlist),
    }

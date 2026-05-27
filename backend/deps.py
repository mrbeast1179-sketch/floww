"""
backend/deps.py

Shared dependencies for route modules.
Extracts common DB connections, auth, and utility functions.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, Request
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")


def get_db():
    """Get MongoDB database connection."""
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]



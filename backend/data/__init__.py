"""
Data layer initialization and migrations.
"""

import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import os
from dotenv import load_dotenv

from data.repositories import (
    GexSnapshotRepository,
    AlertHistoryRepository,
    OrderRepository,
    PositionRepository,
    DataQualityChecker,
)

logger = logging.getLogger(__name__)



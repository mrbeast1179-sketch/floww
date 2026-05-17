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


async def init_data_layer() -> dict:
    """Initialize the data layer with all repositories and indexes."""
    load_dotenv()
    
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]
    
    # Initialize repositories
    gex_repo = GexSnapshotRepository(db)
    alert_repo = AlertHistoryRepository(db)
    order_repo = OrderRepository(db)
    position_repo = PositionRepository(db)
    
    # Create indexes
    await gex_repo.create_indexes()
    await alert_repo.create_indexes()
    await order_repo.create_indexes()
    await position_repo.create_indexes()
    
    logger.info("Data layer initialized")
    
    return {
        "client": client,
        "db": db,
        "gex": gex_repo,
        "alerts": alert_repo,
        "orders": order_repo,
        "positions": position_repo,
        "quality": DataQualityChecker(),
    }


async def run_migrations(db: AsyncIOMotorDatabase):
    """Run database migrations."""
    # Migration 001: Create alerts_history collection
    collections = await db.list_collection_names()
    
    if "alerts_history" not in collections:
        await db.create_collection("alerts_history")
        logger.info("Created alerts_history collection")
    
    if "orders" not in collections:
        await db.create_collection("orders")
        logger.info("Created orders collection")
    
    if "positions" not in collections:
        await db.create_collection("positions")
        logger.info("Created positions collection")
    
    # Create indexes
    await db.alerts_history.create_index([("ticker", 1), ("ts", -1)])
    await db.alerts_history.create_index([("alert_type", 1)])
    await db.orders.create_index([("client_order_id", 1)], unique=True)
    await db.positions.create_index([("ticker", 1), ("status", 1)])
    
    logger.info("Migrations complete")
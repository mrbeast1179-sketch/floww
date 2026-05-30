"""
Data layer initialization and migrations.
"""

import logging

from data.repositories import (
    PositionRepository,  # noqa: F401 — re-exported for module API
)

logger = logging.getLogger(__name__)



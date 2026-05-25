"""
backend/routes/agent_hub.py

Agent Hub CRUD endpoints for managing trading agent archetypes.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent-hub", tags=["agent-hub"])

# In-memory store (persisted to disk by the hub service)
_archetypes: Dict[str, Dict] = {}
_runtime = None


def set_runtime(runtime):
    """Called by server.py to inject the agent hub runtime."""
    global _runtime
    _runtime = runtime


@router.get("/archetypes")
async def list_archetypes():
    """List all agent archetypes."""
    return {"archetypes": list(_archetypes.values())}


@router.get("/archetypes/{name}")
async def get_archetype(name: str):
    """Get a specific archetype by name."""
    if name not in _archetypes:
        raise HTTPException(404, f"Archetype '{name}' not found")
    return _archetypes[name]


@router.post("/archetypes")
async def create_archetype(archetype: Dict[str, Any]):
    """Create a new agent archetype."""
    name = archetype.get("name")
    if not name:
        raise HTTPException(400, "Archetype must have a 'name' field")
    _archetypes[name] = archetype
    return {"status": "created", "name": name}


@router.put("/archetypes/{name}")
async def update_archetype(name: str, archetype: Dict[str, Any]):
    """Update an existing archetype."""
    if name not in _archetypes:
        raise HTTPException(404, f"Archetype '{name}' not found")
    archetype["name"] = name
    _archetypes[name] = archetype
    return {"status": "updated", "name": name}


@router.delete("/archetypes/{name}")
async def delete_archetype(name: str):
    """Delete an archetype."""
    if name not in _archetypes:
        raise HTTPException(404, f"Archetype '{name}' not found")
    del _archetypes[name]
    return {"status": "deleted", "name": name}


@router.post("/archetypes/{name}/enable")
async def enable_archetype(name: str):
    """Enable an archetype."""
    if name not in _archetypes:
        raise HTTPException(404, f"Archetype '{name}' not found")
    _archetypes[name]["enabled"] = True
    return {"status": "enabled", "name": name}


@router.post("/archetypes/{name}/disable")
async def disable_archetype(name: str):
    """Disable an archetype."""
    if name not in _archetypes:
        raise HTTPException(404, f"Archetype '{name}' not found")
    _archetypes[name]["enabled"] = False
    return {"status": "disabled", "name": name}


@router.get("/status")
async def hub_status():
    """Get Agent Hub runtime status."""
    enabled = [n for n, a in _archetypes.items() if a.get("enabled", False)]
    return {
        "total_archetypes": len(_archetypes),
        "enabled": enabled,
        "runtime_running": _runtime is not None,
    }

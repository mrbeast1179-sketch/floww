"""
Redis caching layer for Confluence Decoder API responses.

Caches expensive computations like:
- GEX calculations (5-min TTL)
- Options chain data (1-min TTL)
- Spot prices (10-sec TTL)
- Alert summaries (30-sec TTL)
"""

import os
import json
import logging
import hashlib
from functools import wraps

logger = logging.getLogger(__name__)

_redis_client = None


def get_redis_client():
    """Get or create Redis client."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    
    try:
        import redis.asyncio as redis
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        _redis_client = redis.from_url(redis_url, decode_responses=True)
        logger.info(f"Redis client initialized: {redis_url}")
    except ImportError:
        logger.warning("redis package not installed — caching disabled")
        return None
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e}")
        return None
    
    return _redis_client


def cache_response(ttl: int = 60, key_prefix: str = "api"):
    """Decorator to cache API response in Redis."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            client = get_redis_client()
            if not client:
                return await func(*args, **kwargs)
            
            # Build cache key from function name and arguments
            cache_key = f"{key_prefix}:{func.__name__}"
            for arg in args:
                if isinstance(arg, str):
                    cache_key += f":{arg}"
            for k, v in sorted(kwargs.items()):
                cache_key += f":{k}={v}"
            
            # Hash long keys
            if len(cache_key) > 200:
                cache_key = f"{key_prefix}:{func.__name__}:{hashlib.md5(cache_key.encode()).hexdigest()}"
            
            try:
                # Try to get from cache
                cached = await client.get(cache_key)
                if cached:
                    logger.debug(f"Cache hit: {cache_key}")
                    return json.loads(cached)
            except Exception as e:
                logger.debug(f"Cache read error: {e}")
            
            # Call the actual function
            result = await func(*args, **kwargs)
            
            # Store in cache
            try:
                await client.setex(cache_key, ttl, json.dumps(result, default=str))
                logger.debug(f"Cache set: {cache_key} (TTL={ttl}s)")
            except Exception as e:
                logger.debug(f"Cache write error: {e}")
            
            return result
        return wrapper
    return decorator


async def invalidate_cache(pattern: str = "api:*"):
    """Invalidate cached entries matching a pattern."""
    client = get_redis_client()
    if not client:
        return
    
    try:
        keys = []
        async for key in client.scan_iter(match=pattern):
            keys.append(key)
        if keys:
            await client.delete(*keys)
            logger.info(f"Invalidated {len(keys)} cache entries matching {pattern}")
    except Exception as e:
        logger.warning(f"Cache invalidation error: {e}")
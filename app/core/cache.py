import json
import redis.asyncio as redis
from app.core.config import settings

redis_client: redis.Redis | None = None


async def init_redis():
    global redis_client
    redis_client = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=3,
        socket_connect_timeout=3,
    )


async def close_redis():
    if redis_client:
        await redis_client.close()


async def check_redis() -> bool:
    try:
        await redis_client.ping()
        return True
    except Exception:
        return False


async def check_rate_limit(api_key: str, limit: int = 30, window_seconds: int = 60) -> bool:
    """Fails open if Redis (Upstash) is unreachable."""
    try:
        key = f"ratelimit:{api_key}"
        current = await redis_client.incr(key)
        if current == 1:
            await redis_client.expire(key, window_seconds)
        return current <= limit
    except Exception:
        return True


async def get_cached_explanation(workflow_id: str) -> str | None:
    try:
        return await redis_client.get(f"explain:{workflow_id}")
    except Exception:
        return None


async def cache_explanation(workflow_id: str, explanation: str, ttl_seconds: int = 300):
    try:
        await redis_client.set(f"explain:{workflow_id}", explanation, ex=ttl_seconds)
    except Exception:
        pass


async def invalidate_explanation(workflow_id: str):
    """Call this whenever a workflow is modified/fixed — a cached
    explanation of the old version would otherwise be served stale."""
    try:
        await redis_client.delete(f"explain:{workflow_id}")
    except Exception:
        pass


async def cache_execution_result(workflow_id: str, result: dict, ttl_seconds: int = 86400):
    """Stores the most recent execution result for a workflow so
    repeated GETs don't need to re-run or re-query Postgres."""
    try:
        await redis_client.set(f"execution:{workflow_id}:latest", json.dumps(result), ex=ttl_seconds)
    except Exception:
        pass


async def get_cached_execution_result(workflow_id: str) -> dict | None:
    try:
        raw = await redis_client.get(f"execution:{workflow_id}:latest")
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def acquire_execution_lock(workflow_id: str, ttl_seconds: int = 30) -> bool:
    """Prevents the same workflow being executed concurrently twice
    (e.g. a user double-clicking 'Run'). Returns True if the lock was
    acquired, False if another execution is already in progress.
    Fails open (allows execution) if Redis is unreachable.
    """
    try:
        return bool(await redis_client.set(f"lock:execution:{workflow_id}", "1", nx=True, ex=ttl_seconds))
    except Exception:
        return True


async def release_execution_lock(workflow_id: str):
    try:
        await redis_client.delete(f"lock:execution:{workflow_id}")
    except Exception:
        pass
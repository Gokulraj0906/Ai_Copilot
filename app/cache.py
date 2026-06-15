import redis.asyncio as redis
from app.config import settings

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
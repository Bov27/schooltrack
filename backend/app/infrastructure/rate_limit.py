"""Failed-login throttling in Redis (fixed window per key).

Fails open: if Redis is unreachable, logins are not blocked (availability first) and a
warning is logged. With REDIS_URL unset the limiter is disabled entirely.
"""

import hashlib
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger("schooltrack.rate_limit")


def _key(scope: str, value: str) -> str:
    # Hash so that emails and IPs are not stored in clear text in Redis.
    digest = hashlib.sha256(value.encode()).hexdigest()[:32]
    return f"schooltrack:ratelimit:{scope}:{digest}"


class LoginRateLimiter:
    def __init__(self, redis: Redis | None, *, max_attempts: int, window_s: int) -> None:
        self.redis = redis
        self.max_attempts = max_attempts
        self.window_s = window_s

    async def retry_after(self, email: str, ip: str | None) -> int | None:
        """Seconds until a new attempt is allowed, or None if allowed now."""
        if self.redis is None:
            return None
        try:
            for key in self._keys(email, ip):
                count = await self.redis.get(key)
                if count is not None and int(count) >= self.max_attempts:
                    ttl = await self.redis.ttl(key)
                    return max(int(ttl), 1)
        except RedisError as exc:
            logger.warning("rate limiter unavailable: %s", exc)
        return None

    async def record_failure(self, email: str, ip: str | None) -> None:
        if self.redis is None:
            return
        try:
            for key in self._keys(email, ip):
                count = await self.redis.incr(key)
                if count == 1:
                    await self.redis.expire(key, self.window_s)
        except RedisError as exc:
            logger.warning("rate limiter unavailable: %s", exc)

    async def reset(self, email: str) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.delete(_key("email", email))
        except RedisError as exc:
            logger.warning("rate limiter unavailable: %s", exc)

    def _keys(self, email: str, ip: str | None) -> list[str]:
        keys = [_key("email", email)]
        if ip:
            keys.append(_key("ip", ip))
        return keys

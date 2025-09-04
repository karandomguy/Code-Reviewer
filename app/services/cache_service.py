import json
import asyncio
from typing import Optional, Dict, Any
from redis import Redis
from cachetools import TTLCache
from app.config import settings
from app.utils.logging import logger

class CacheService:
    def __init__(self):
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)
        self.local_cache = TTLCache(maxsize=1000, ttl=300)  # 5min local cache
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache (L1: local, L2: Redis)."""
        try:
            # L1: Local cache
            if key in self.local_cache:
                logger.debug("Cache hit (local)", key=key)
                return self.local_cache[key]
            
            # L2: Redis cache
            cached = await asyncio.get_event_loop().run_in_executor(
                None, self.redis.get, key
            )
            if cached:
                result = json.loads(cached)
                self.local_cache[key] = result
                logger.debug("Cache hit (redis)", key=key)
                return result
            
            logger.debug("Cache miss", key=key)
            return None
            
        except Exception as e:
            logger.error("Cache get error", key=key, error=str(e))
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Set value in cache with TTL."""
        try:
            # Set in Redis
            await asyncio.get_event_loop().run_in_executor(
                None, self.redis.setex, key, ttl, json.dumps(value)
            )
            
            # Set in local cache
            self.local_cache[key] = value
            logger.debug("Cache set", key=key, ttl=ttl)
            
        except Exception as e:
            logger.error("Cache set error", key=key, error=str(e))
    
    async def delete(self, key: str):
        """Delete key from cache."""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self.redis.delete, key
            )
            self.local_cache.pop(key, None)
            logger.debug("Cache delete", key=key)
            
        except Exception as e:
            logger.error("Cache delete error", key=key, error=str(e))
    
    def get_cache_key(self, prefix: str, **kwargs) -> str:
        """Generate consistent cache key."""
        parts = [prefix] + [f"{k}:{v}" for k, v in sorted(kwargs.items())]
        return ":".join(parts)
    
    async def get_pr_analysis(self, repo: str, pr_number: int, commit_sha: str) -> Optional[Dict]:
        """Get cached PR analysis result."""
        key = self.get_cache_key("analysis", repo=repo, pr=pr_number, sha=commit_sha)
        return await self.get(key)
    
    async def cache_pr_analysis(self, repo: str, pr_number: int, commit_sha: str, 
                               result: Dict, pr_status: str = "open"):
        """Cache PR analysis result with smart TTL."""
        key = self.get_cache_key("analysis", repo=repo, pr=pr_number, sha=commit_sha)
        
        # Smart TTL based on PR status
        ttl = 3600 if pr_status == "open" else 86400  # 1hr for open, 24hr for closed
        
        await self.set(key, result, ttl)

cache_service = CacheService()
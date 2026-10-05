package com.echo.service;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

/**
 * Fixed-window counters in Redis (shared across backend instances), with an in-memory fallback so a Redis
 * outage degrades to per-instance limits instead of failing requests.
 */
@Service
public class RateLimiter {

    private static final Logger log = LoggerFactory.getLogger(RateLimiter.class);

    private final StringRedisTemplate redis;
    private final Map<String, long[]> local = new ConcurrentHashMap<>();

    public RateLimiter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    /** True if the call is allowed; counts it either way. */
    public boolean tryAcquire(String key, int limit, Duration window) {
        long bucket = Instant.now().getEpochSecond() / window.getSeconds();
        String redisKey = "echo:rl:" + key + ":" + bucket;
        try {
            Long count = redis.opsForValue().increment(redisKey);
            if (count != null && count == 1L) {
                redis.expire(redisKey, window);
            }
            return count != null && count <= limit;
        } catch (RuntimeException e) {
            log.debug("Redis unavailable for rate limiting ({}); using local counter", e.getMessage());
            long[] slot = local.compute(redisKey, (k, v) -> v == null ? new long[] {0} : v);
            synchronized (slot) {
                slot[0]++;
                return slot[0] <= limit;
            }
        }
    }
}

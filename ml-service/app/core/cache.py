"""Raw-response cache (ARCHITECTURE §4): Redis when reachable, otherwise an in-process TTL dict."""

from __future__ import annotations

import gzip
import json
import logging
import threading
import time
from typing import Any

log = logging.getLogger(__name__)


class ResponseCache:
    def __init__(self, host: str, port: int, enabled: bool = True, prefix: str = "echo:ml:"):
        self._prefix = prefix
        self._local: dict[str, tuple[float, bytes]] = {}
        self._lock = threading.Lock()
        self._redis = None
        if enabled:
            try:
                import redis

                client = redis.Redis(host=host, port=port, socket_connect_timeout=1, socket_timeout=2)
                client.ping()
                self._redis = client
            except Exception as exc:  # Redis is an optimisation, never a hard dependency
                log.info("Redis unavailable (%s); using in-process cache", exc)

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    def get_json(self, key: str) -> Any | None:
        raw = None
        if self._redis is not None:
            try:
                raw = self._redis.get(self._prefix + key)
            except Exception:
                raw = None
        else:
            with self._lock:
                hit = self._local.get(key)
                if hit and hit[0] > time.monotonic():
                    raw = hit[1]
        return json.loads(gzip.decompress(raw)) if raw else None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        raw = gzip.compress(json.dumps(value).encode())
        if self._redis is not None:
            try:
                self._redis.setex(self._prefix + key, ttl_seconds, raw)
                return
            except Exception:
                pass
        with self._lock:
            self._local[key] = (time.monotonic() + ttl_seconds, raw)

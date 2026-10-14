"""Limite de taxa em memória por janela deslizante (SEC-08).

Válido para uma instância (DT-009). Com várias instâncias, usar armazenamento
compartilhado.
"""

import threading
from collections import defaultdict, deque

from app.core import clock
from app.core.errors import ProblemError


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, window: float, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and hits[0] <= now - window:
            hits.popleft()
        return hits

    def hit(self, key: str, limit: int, window_seconds: float) -> None:
        """Registra uma tentativa e levanta 429 se o limite foi excedido."""
        now = clock.now().timestamp()
        with self._lock:
            hits = self._prune(key, window_seconds, now)
            if len(hits) >= limit:
                retry = int(hits[0] + window_seconds - now) + 1
                raise ProblemError(
                    429, "rate_limited", "Muitas tentativas",
                    "Aguarde um pouco e tente novamente.", {"Retry-After": str(retry)},
                )
            hits.append(now)

    def count(self, key: str, window_seconds: float) -> int:
        with self._lock:
            return len(self._prune(key, window_seconds, clock.now().timestamp()))

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()

"""
Event bus for YTSage Web UI WebSocket broadcasting.
Extracted from DownloadManager so all subsystems (downloads, updater,
commands) share one broadcast channel with per-client queue backpressure.
"""

import asyncio
from typing import Any, Dict, List, Optional


class EventBus:
    """Fan-out async event bus with per-subscriber bounded queues."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._queues: List[asyncio.Queue] = []
        self._maxsize = maxsize

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._queues:
            self._queues.remove(q)

    def publish(self, event: Dict[str, Any]) -> None:
        """Non-blocking best-effort publish. Drops events for full queues."""
        for q in list(self._queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest intermediate event to make room
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass
            except Exception:
                pass

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)


class ThrottledPublisher:
    """Rate-limits publishing of intermediate updates (e.g. progress lines).

    Terminal events should bypass throttling via `flush()`.
    """

    def __init__(self, bus: EventBus, interval: float = 0.1) -> None:
        self._bus = bus
        self._interval = interval
        self._last_emit: Dict[str, float] = {}
        self._pending: Dict[str, Optional[Dict[str, Any]]] = {}
        self._timers: Dict[str, Optional[asyncio.TimerHandle]] = {}

    def publish(self, key: str, event: Dict[str, Any], now: float) -> None:
        last = self._last_emit.get(key, 0.0)
        if now - last >= self._interval:
            self._last_emit[key] = now
            self._bus.publish(event)
        else:
            # Schedule a trailing emit so the latest state is always delivered
            self._pending[key] = event
            if key not in self._timers or self._timers[key] is None:
                loop = asyncio.get_running_loop()
                delay = self._interval - (now - last)
                self._timers[key] = loop.call_later(delay, self._flush_key, key)

    def _flush_key(self, key: str) -> None:
        event = self._pending.pop(key, None)
        self._timers[key] = None
        if event is not None:
            import time as _t
            self._last_emit[key] = _t.time()
            self._bus.publish(event)

    def flush(self, key: str, event: Dict[str, Any]) -> None:
        """Emit immediately (for terminal events), cancelling any pending."""
        timer = self._timers.get(key)
        if timer is not None:
            timer.cancel()
            self._timers[key] = None
        self._pending.pop(key, None)
        import time as _t
        self._last_emit[key] = _t.time()
        self._bus.publish(event)

    def cleanup(self, key: str) -> None:
        timer = self._timers.pop(key, None)
        if timer is not None:
            timer.cancel()
        self._pending.pop(key, None)
        self._last_emit.pop(key, None)


bus = EventBus()
throttled = ThrottledPublisher(bus)

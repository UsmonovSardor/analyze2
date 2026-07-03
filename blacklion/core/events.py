"""In-process event bus (SRS doc 02 §14).

v1 (monolith) uses synchronous in-process pub/sub with the same event names the
SRS defines (NewCandle, LiquiditySweep, TradeExecuted, RiskLimitHit ...), so the
transport can later be swapped for RabbitMQ/Kafka without touching publishers
or subscribers. A failing subscriber never breaks the publisher (doc 02 §15).
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from .logging import get_logger

log = get_logger("core.events")


@dataclass(frozen=True)
class Event:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    ts: float = field(default_factory=time.time)


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[Event], None]]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        self._subs[event_type].append(handler)

    def publish(self, event_type: str, **payload: Any) -> Event:
        event = Event(type=event_type, payload=payload)
        for handler in self._subs.get(event_type, []):
            try:
                handler(event)
            except Exception:
                log.exception("SubscriberFailed", event=event_type,
                              handler=getattr(handler, "__qualname__", str(handler)))
        return event


bus = EventBus()

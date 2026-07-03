"""Shared market-data models (SRS docs 06 §5, 08 §5)."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Timeframe(StrEnum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
    MN = "MN"

    @property
    def minutes(self) -> int:
        return {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60,
                "H4": 240, "D1": 1440, "W1": 10080, "MN": 43200}[self.value]


class Candle(BaseModel):
    """Normalized market snapshot — immutable (doc 08 §17)."""
    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: Timeframe
    timestamp: datetime          # UTC, ISO-8601
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread: float = 0.0

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def bullish(self) -> bool:
        return self.close >= self.open

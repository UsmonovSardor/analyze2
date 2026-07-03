"""Data Normalizer (SRS doc 08) — one unified internal format.

Symbol aliases, timeframe aliases, UTC timestamps, configured decimal precision.
No business logic here (doc 08 §17).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..core import config
from .models import Candle, Timeframe

_TF_ALIASES: dict[str, Timeframe] = {
    "1m": Timeframe.M1, "m1": Timeframe.M1, "1": Timeframe.M1,
    "5m": Timeframe.M5, "m5": Timeframe.M5, "5": Timeframe.M5,
    "15m": Timeframe.M15, "m15": Timeframe.M15, "15": Timeframe.M15,
    "30m": Timeframe.M30, "m30": Timeframe.M30, "30": Timeframe.M30,
    "60": Timeframe.H1, "1h": Timeframe.H1, "h1": Timeframe.H1,
    "240": Timeframe.H4, "4h": Timeframe.H4, "h4": Timeframe.H4,
    "1d": Timeframe.D1, "d1": Timeframe.D1, "d": Timeframe.D1,
    "1w": Timeframe.W1, "w1": Timeframe.W1,
    "1mn": Timeframe.MN, "mn": Timeframe.MN,
}


class NormalizationError(Exception):
    pass


def normalize_symbol(raw: str) -> str:
    raw = raw.strip()
    cfg = config.load("symbols")
    aliases = {k.upper(): v for k, v in (cfg.get("aliases") or {}).items()}
    symbol = aliases.get(raw.upper(), raw.upper())
    if symbol not in cfg["symbols"]:
        raise NormalizationError(f"UNKNOWN_SYMBOL: {raw}")
    return symbol


def normalize_timeframe(raw: str) -> Timeframe:
    key = raw.strip().lower()
    try:
        return Timeframe(raw.strip().upper())
    except ValueError:
        pass
    if key in _TF_ALIASES:
        return _TF_ALIASES[key]
    raise NormalizationError(f"INVALID_TIMEFRAME: {raw}")


def normalize_timestamp(raw: datetime | int | float | str) -> datetime:
    """Any broker timestamp → aware UTC datetime."""
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    if isinstance(raw, str):
        dt = datetime.fromisoformat(raw)
    else:
        dt = raw
    if dt.tzinfo is None:
        raise NormalizationError("INVALID_TIMEZONE: naive timestamp")
    return dt.astimezone(timezone.utc)


def normalize_candle(raw: dict[str, Any]) -> Candle:
    """Raw broker payload → immutable normalized Candle (doc 08 §5)."""
    symbol = normalize_symbol(str(raw["symbol"]))
    digits = config.load("symbols")["symbols"][symbol].get("digits", 5)
    return Candle(
        symbol=symbol,
        timeframe=normalize_timeframe(str(raw["timeframe"])),
        timestamp=normalize_timestamp(raw["timestamp"]),
        open=round(float(raw["open"]), digits),
        high=round(float(raw["high"]), digits),
        low=round(float(raw["low"]), digits),
        close=round(float(raw["close"]), digits),
        volume=float(raw.get("volume", 0.0)),
        spread=float(raw.get("spread", 0.0)),
    )

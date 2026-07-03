"""Data Validation Engine (SRS doc 07).

No downstream engine may consume unvalidated data. Pure functions: candle in,
verdict out. Error codes match doc 07 §18 exactly.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

from ..core import config
from .models import Candle


class Verdict(BaseModel):
    valid: bool
    issues: list[str] = []

    @classmethod
    def ok(cls) -> "Verdict":
        return cls(valid=True)

    @classmethod
    def reject(cls, *codes: str) -> "Verdict":
        return cls(valid=False, issues=list(codes))


def validate_candle(candle: Candle, prev_timestamp: datetime | None = None) -> Verdict:
    """Full doc 07 pipeline: schema is enforced by pydantic; here OHLC, time,
    spread, symbol, timeframe-alignment and ordering rules."""
    issues: list[str] = []
    symbols = config.load("symbols")["symbols"]

    if candle.symbol not in symbols:
        issues.append("INVALID_SYMBOL")

    # OHLC rules (doc 07 §8)
    if candle.high < candle.low:
        issues.append("INVALID_HIGH")
    if not (candle.low <= candle.open <= candle.high):
        issues.append("INVALID_OPEN")
    if not (candle.low <= candle.close <= candle.high):
        issues.append("INVALID_CLOSE")
    if candle.open <= 0 or candle.close <= 0:
        issues.append("INVALID_CLOSE" if candle.close <= 0 else "INVALID_OPEN")
    if candle.volume < 0:
        issues.append("INVALID_VOLUME")

    # Timestamp rules (doc 07 §9)
    ts = candle.timestamp
    if ts.tzinfo is None:
        issues.append("INVALID_TIMESTAMP")
    else:
        now = datetime.now(timezone.utc)
        if ts > now:
            issues.append("INVALID_TIMESTAMP")
        tf_min = candle.timeframe.minutes
        if tf_min <= 1440 and (ts.minute * 60 + ts.second) % (tf_min * 60) not in (0,):
            # candle open must align to its timeframe grid (intraday TFs)
            total_min = ts.hour * 60 + ts.minute
            if total_min % tf_min != 0 or ts.second != 0:
                issues.append("INVALID_TIMESTAMP")
        if prev_timestamp is not None:
            if ts == prev_timestamp:
                issues.append("DUPLICATE_CANDLE")
            elif ts < prev_timestamp:
                issues.append("INVALID_TIMESTAMP")

    # Spread rule (doc 07 §12) — 0 in config disables the check (crypto)
    max_spread = symbols.get(candle.symbol, {}).get("max_spread_points", 0)
    if max_spread and candle.spread > max_spread:
        issues.append("SPREAD_TOO_HIGH")

    # deduplicate, preserve order
    issues = list(dict.fromkeys(issues))
    return Verdict(valid=not issues, issues=issues)


def detect_gap(prev: Candle, cur: Candle) -> bool:
    """Missing-candle detection (doc 07 §15). Weekend/holiday gaps are the
    caller's concern (session calendar); this flags a raw grid gap."""
    expected = prev.timestamp.timestamp() + prev.timeframe.minutes * 60
    return cur.timestamp.timestamp() > expected

"""Nison candlestick + Brooks bar-quality helpers
(docs/strategies/candlestick-patterns.md, price-action.md).

Pure functions over the last bars of an OHLC frame. Every threshold follows the
catalog text (hammer = lower shadow ≥ 2× body; strong trend bar = body ≥ 60% of
range closing in the top/bottom 25%; absorption wick = counter-wick > 60%).
"""
from __future__ import annotations

import pandas as pd


def _bar(df: pd.DataFrame, i: int) -> tuple[float, float, float, float]:
    row = df.iloc[i]
    return float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])


def _body(o: float, c: float) -> float:
    return abs(c - o)


def _rng(h: float, low: float) -> float:
    return (h - low) or 1e-12


def is_hammer(df: pd.DataFrame, i: int = -1) -> bool:
    o, h, low, c = _bar(df, i)
    body = _body(o, c)
    lower = min(o, c) - low
    upper = h - max(o, c)
    return body > 0 and lower >= 2 * body and upper <= body


def is_shooting_star(df: pd.DataFrame, i: int = -1) -> bool:
    o, h, low, c = _bar(df, i)
    body = _body(o, c)
    upper = h - max(o, c)
    lower = min(o, c) - low
    return body > 0 and upper >= 2 * body and lower <= body


def is_bullish_engulfing(df: pd.DataFrame, i: int = -1) -> bool:
    po, _, _, pc = _bar(df, i - 1)
    o, _, _, c = _bar(df, i)
    return pc < po and c > o and o <= pc and c >= po


def is_bearish_engulfing(df: pd.DataFrame, i: int = -1) -> bool:
    po, _, _, pc = _bar(df, i - 1)
    o, _, _, c = _bar(df, i)
    return pc > po and c < o and o >= pc and c <= po


def is_piercing(df: pd.DataFrame, i: int = -1) -> bool:
    """Bull bar closing above the midpoint of the prior bear bar (Nison)."""
    po, _, _, pc = _bar(df, i - 1)
    o, _, _, c = _bar(df, i)
    mid = (po + pc) / 2
    return pc < po and c > o and c > mid


def is_dark_cloud(df: pd.DataFrame, i: int = -1) -> bool:
    po, _, _, pc = _bar(df, i - 1)
    o, _, _, c = _bar(df, i)
    mid = (po + pc) / 2
    return pc > po and c < o and c < mid


def is_strong_trend_bar(df: pd.DataFrame, direction: str, i: int = -1) -> bool:
    """Brooks: body ≥ 60% of range, closing in the extreme 25% of the bar."""
    o, h, low, c = _bar(df, i)
    rng = _rng(h, low)
    if _body(o, c) / rng < 0.60:
        return False
    if direction == "BUY":
        return c > o and (h - c) / rng <= 0.25
    return c < o and (c - low) / rng <= 0.25


def is_morning_star(df: pd.DataFrame, i: int = -1) -> bool:
    o1, _, _, c1 = _bar(df, i - 2)     # bear bar
    o2, _, _, c2 = _bar(df, i - 1)     # small-body star
    o3, _, _, c3 = _bar(df, i)         # bull bar into bar-1's body
    return (c1 < o1 and _body(o2, c2) < _body(o1, c1) * 0.5
            and c3 > o3 and c3 > (o1 + c1) / 2)


def is_evening_star(df: pd.DataFrame, i: int = -1) -> bool:
    o1, _, _, c1 = _bar(df, i - 2)
    o2, _, _, c2 = _bar(df, i - 1)
    o3, _, _, c3 = _bar(df, i)
    return (c1 > o1 and _body(o2, c2) < _body(o1, c1) * 0.5
            and c3 < o3 and c3 < (o1 + c1) / 2)


def wick_against(df: pd.DataFrame, direction: str, i: int = -1) -> bool:
    """Absorption: counter-wick > 60% of the bar's range — supply above a long /
    demand below a short. Hard rejection per the catalog."""
    o, h, low, c = _bar(df, i)
    rng = _rng(h, low)
    if direction == "BUY":
        return (h - max(o, c)) / rng > 0.60
    return (min(o, c) - low) / rng > 0.60


def bullish_confirmation(df: pd.DataFrame) -> str | None:
    """Name of the bullish trigger pattern on the signal bar, if any."""
    if len(df) >= 3 and is_morning_star(df):
        return "morning star"
    if len(df) >= 2 and is_bullish_engulfing(df):
        return "bullish engulfing"
    if len(df) >= 2 and is_piercing(df):
        return "piercing"
    if is_hammer(df):
        return "hammer"
    if is_strong_trend_bar(df, "BUY"):
        return "strong bull bar"
    return None


def bearish_confirmation(df: pd.DataFrame) -> str | None:
    if len(df) >= 3 and is_evening_star(df):
        return "evening star"
    if len(df) >= 2 and is_bearish_engulfing(df):
        return "bearish engulfing"
    if len(df) >= 2 and is_dark_cloud(df):
        return "dark cloud cover"
    if is_shooting_star(df):
        return "shooting star"
    if is_strong_trend_bar(df, "SELL"):
        return "strong bear bar"
    return None

"""Synthetic OHLC builders shared across engine tests."""
from __future__ import annotations

import numpy as np
import pandas as pd


def df_from_closes(closes: list[float], wick: float = 0.3) -> pd.DataFrame:
    c = np.asarray(closes, dtype=float)
    o = np.roll(c, 1)
    o[0] = c[0]
    high = np.maximum(o, c) + wick
    low = np.minimum(o, c) - wick
    df = pd.DataFrame({"open": o, "high": high, "low": low, "close": c, "volume": 1000.0})
    df["atr"] = (high - low)
    df["atr"] = df["atr"].ewm(alpha=1 / 14, adjust=False).mean()
    return df


def zigzag(levels: list[float], leg: int = 8) -> list[float]:
    out: list[float] = [levels[0]]
    for a, b in zip(levels, levels[1:]):
        out += list(np.linspace(a, b, leg + 1)[1:])
    return out


def df_from_ohlc(rows: list[tuple[float, float, float, float]],
                 volume: float = 1000.0) -> pd.DataFrame:
    """rows: list of (open, high, low, close)."""
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df["volume"] = volume
    tr = df["high"] - df["low"]
    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    return df

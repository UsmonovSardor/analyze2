"""Deterministic indicator enrichment (SRS doc 09 base features).

Adds the columns every engine reads (atr) plus the trend/momentum basics the
Feature Engineering Engine will build on. Pure function of the input frame —
same candles in, same indicators out (doc 09 §23).
"""
from __future__ import annotations

import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Enrich an OHLCV frame in place-safe fashion; returns a new frame with
    atr, ema20/50/200 and rsi. Expects columns open/high/low/close/volume."""
    out = df.copy()
    c = out["close"]

    # EMAs (trend)
    out["ema20"] = c.ewm(span=20, adjust=False).mean()
    out["ema50"] = c.ewm(span=50, adjust=False).mean()
    out["ema200"] = c.ewm(span=200, adjust=False).mean()

    # Wilder ATR (volatility) — the column engines depend on
    prev_close = c.shift()
    tr = pd.concat([
        out["high"] - out["low"],
        (out["high"] - prev_close).abs(),
        (out["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    out["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()

    # Wilder RSI (momentum) — used later by feature engineering
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-12)
    out["rsi"] = 100 - 100 / (1 + rs)

    out["vol_avg20"] = out["volume"].rolling(20).mean()
    return out

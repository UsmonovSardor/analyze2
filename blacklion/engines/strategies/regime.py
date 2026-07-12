"""Market regime classifier (docs/strategies/strategy.md §Market Regime).

Five regimes drive which setups are allowed; High-Volatility Chop rejects
EVERYTHING (Livermore: "There are times when I won't do anything").
Deterministic: EMA50/EMA200 alignment + ATR expansion, mirrored for bears.
"""
from __future__ import annotations

import pandas as pd

from .base import Regime

# ATR spiking beyond this multiple of its own recent average = chop (huge wicks,
# no tradeable structure). strategy.md says "> 2× normal".
CHOP_ATR_RATIO = 2.0


def classify_regime(df: pd.DataFrame) -> Regime:
    if not {"close", "ema50", "ema200", "atr"} <= set(df.columns) or len(df) < 60:
        return "range"                              # not enough context — neutral

    close = float(df["close"].iloc[-1])
    ema50 = float(df["ema50"].iloc[-1])
    ema200 = float(df["ema200"].iloc[-1])
    atr = float(df["atr"].iloc[-1])
    atr_avg = float(df["atr"].tail(50).mean()) or atr

    if atr_avg > 0 and atr / atr_avg > CHOP_ATR_RATIO:
        return "chop"

    if close > ema200 and ema50 > ema200:
        # bull: above EMA50 too = riding the trend; testing EMA50 = pullback phase
        return "strong_bull" if close > ema50 else "bull_pullback"
    if close < ema200 and ema50 < ema200:
        return "strong_bear" if close < ema50 else "bear_rally"
    return "range"                                   # transition / consolidation


def regime_allows(regime: Regime, direction: str) -> bool:
    """Hard directional gate per the catalog: no longs in a bear regime, no
    shorts in a bull regime; chop allows nothing; range allows breakouts both
    ways (Setup B decides)."""
    if regime == "chop":
        return False
    if direction == "BUY":
        return regime in ("strong_bull", "bull_pullback", "range")
    return regime in ("strong_bear", "bear_rally", "range")

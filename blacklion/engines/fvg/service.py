"""Fair Value Gap Engine (SRS doc 13).

A Bullish FVG exists on a 3-candle pattern when high(candle1) < low(candle3),
leaving an untraded gap; bearish is the mirror (low1 > high3). Tracks fill
percentage and lifecycle. Provides validated FVG zones to the Rule Engine.
"""
from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel

from ...core import config
from ...core.events import bus
from ...core.logging import get_logger

log = get_logger("engines.fvg")


class FairValueGap(BaseModel):
    type: Literal["bullish", "bearish"]
    index: int                       # index of the middle (displacement) candle
    gap_low: float
    gap_high: float
    size: float
    filled_pct: float
    filled: bool
    score: int
    quality: str
    confidence: int                  # doc 13 §4 — calibrated 0–100

    @property
    def midpoint(self) -> float:
        return (self.gap_low + self.gap_high) / 2


class FVGResult(BaseModel):
    symbol: str
    active: list[FairValueGap] = []
    nearest: FairValueGap | None = None


def _grade(score: int) -> str:
    return ("A+" if score >= 90 else "A" if score >= 80 else "B" if score >= 65
            else "C" if score >= 50 else "D")


class FVGEngine:
    def __init__(self) -> None:
        cfg = config.engine("fvg")
        self.min_gap_atr: float = float(cfg.get("minimum_gap_atr", 0.15))
        self.min_score: int = int(cfg.get("minimum_score", 70))
        self.max_age: int = int(cfg.get("maximum_gap_age_bars", 500))

    def analyze(self, symbol: str, df: pd.DataFrame) -> FVGResult:
        atr = float(df["atr"].iloc[-1]) if "atr" in df and df["atr"].iloc[-1] > 0 else \
            float((df["high"] - df["low"]).tail(14).mean())
        high, low, o, c = (df["high"].values, df["low"].values,
                           df["open"].values, df["close"].values)
        n = len(df)
        close = float(c[-1])
        gaps: list[FairValueGap] = []
        min_gap = self.min_gap_atr * atr

        for i in range(1, n - 1):
            if n - i > self.max_age:
                continue
            # bullish FVG: candle i-1 high below candle i+1 low
            if high[i - 1] < low[i + 1] and (low[i + 1] - high[i - 1]) >= min_gap:
                lo, hi = float(high[i - 1]), float(low[i + 1])
                g = self._build("bullish", i, lo, hi, atr, o[i], c[i], high, low, n, close)
                if g.score >= self.min_score:
                    gaps.append(g)
            # bearish FVG: candle i-1 low above candle i+1 high
            elif low[i - 1] > high[i + 1] and (low[i - 1] - high[i + 1]) >= min_gap:
                lo, hi = float(high[i + 1]), float(low[i - 1])
                g = self._build("bearish", i, lo, hi, atr, o[i], c[i], high, low, n, close)
                if g.score >= self.min_score:
                    gaps.append(g)

        active = [g for g in gaps if not g.filled]
        nearest = min(active, key=lambda g: abs(g.midpoint - close), default=None)
        for g in active[-8:]:
            bus.publish("BullishFVGDetected" if g.type == "bullish"
                        else "BearishFVGDetected",
                        symbol=symbol, zone=[g.gap_low, g.gap_high])
        return FVGResult(symbol=symbol, active=active[-8:], nearest=nearest)

    def _build(self, kind, i, lo, hi, atr, o_i, c_i, high, low, n, close) -> FairValueGap:
        size = hi - lo
        # fill: how far later candles have retraced into the gap
        after_lo = low[i + 1:]
        after_hi = high[i + 1:]
        if kind == "bullish":
            deepest = float(after_lo.min()) if len(after_lo) else hi
            filled_pct = max(0.0, min(1.0, (hi - deepest) / (size or 1e-9)))
        else:
            deepest = float(after_hi.max()) if len(after_hi) else lo
            filled_pct = max(0.0, min(1.0, (deepest - lo) / (size or 1e-9)))
        filled = filled_pct >= 0.99

        disp_body = abs(c_i - o_i)
        score = 45.0
        score += min(25, 25 * (size / atr) / 0.5)                 # gap size vs ATR
        score += min(20, 20 * (disp_body / atr))                  # displacement strength
        score += 10 * (1 - filled_pct)                            # freshness
        score = max(0, min(100, round(score)))
        return FairValueGap(type=kind, index=i, gap_low=lo, gap_high=hi, size=size,
                            filled_pct=round(filled_pct, 3), filled=filled,
                            score=score, quality=_grade(score), confidence=score)

"""Manipulation / Trap / Inducement engine (TITAN Bible ch.8).

Institutions take liquidity BEFORE the real move (8.12) and induce retail into the
wrong entry (8.13). This engine flags:

  • Fake breakout / trap (8.11/8.14): a bar whose WICK broke a prior swing extreme
    but whose BODY closed back inside — buyers/sellers trapped. If the signal
    would join the TRAPPED side, the Rule Engine rejects it; if the trap points
    the OTHER way it CONFIRMS the reversal.
  • Inducement (8.13): a minor opposite-side liquidity grab (stop hunt) right
    before structure breaks our way — an institutional footprint, confidence up.

Deterministic over OHLC(+volume); no lookahead.
"""
from __future__ import annotations

import pandas as pd
from pydantic import BaseModel

from ..core.logging import get_logger

log = get_logger("engines.manipulation")


class ManipulationResult(BaseModel):
    symbol: str
    bull_trap: bool = False           # up-break that failed → traps buyers (bearish)
    bear_trap: bool = False           # down-break that failed → traps sellers (bullish)
    trapped_direction: str = ""       # "BUY" | "SELL" — the side that got trapped
    inducement: bool = False          # minor sweep before the real move
    manip_score: int = 0              # 0–100


class ManipulationEngine:
    def __init__(self, recent: int = 4, swing_lookback: int = 20,
                 vol_expand: float = 1.2) -> None:
        self.recent = recent               # bars in which the trap must be fresh
        self.swing_lookback = swing_lookback
        self.vol_expand = vol_expand

    def analyze(self, symbol: str, df: pd.DataFrame,
                liquidity=None) -> ManipulationResult:
        if not {"high", "low", "close"} <= set(df.columns) \
                or len(df) < self.swing_lookback + self.recent + 2:
            return ManipulationResult(symbol=symbol)

        high = df["high"].to_numpy(float)
        low = df["low"].to_numpy(float)
        close = df["close"].to_numpy(float)
        vol = df["volume"].to_numpy(float) if "volume" in df else None
        n = len(df)

        bull_trap = bear_trap = False
        for i in range(n - self.recent, n):
            if i <= self.swing_lookback:
                continue
            prior_high = float(high[i - self.swing_lookback:i].max())
            prior_low = float(low[i - self.swing_lookback:i].min())
            weak_vol = True
            if vol is not None:
                avg = float(vol[max(0, i - 20):i].mean()) or 0.0
                weak_vol = avg <= 0 or vol[i] < self.vol_expand * avg
            # bull trap: wick above the prior high, body closed back below it
            if high[i] > prior_high and close[i] < prior_high and weak_vol:
                bull_trap = True
            # bear trap: wick below the prior low, body closed back above it
            if low[i] < prior_low and close[i] > prior_low and weak_vol:
                bear_trap = True

        trapped = "BUY" if bull_trap else "SELL" if bear_trap else ""

        # inducement: a stop-hunt sweep flagged by the Liquidity engine is the
        # classic "grab the obvious liquidity first" footprint (8.12/8.13)
        inducement = bool(liquidity is not None
                          and getattr(liquidity, "stop_hunt", False)
                          and getattr(liquidity, "liquidity_swept", False))

        score = 0
        score += 40 if (bull_trap or bear_trap) else 0
        score += 30 if inducement else 0
        if liquidity is not None and getattr(liquidity, "liquidity_swept", False):
            score += 30
        manip_score = max(0, min(100, score))

        return ManipulationResult(
            symbol=symbol, bull_trap=bull_trap, bear_trap=bear_trap,
            trapped_direction=trapped, inducement=inducement,
            manip_score=manip_score)

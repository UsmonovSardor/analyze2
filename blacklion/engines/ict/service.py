"""ICT Engine (SRS doc 14) — Inner Circle Trader concepts.

Premium/Discount (equilibrium of the dealing range), Optimal Trade Entry (OTE
0.62–0.79 fib), Kill Zones (session timing), Judas Swing, and an aggregate ICT
confluence score. Provides high-confidence context to the Rule Engine.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Literal

import pandas as pd
from pydantic import BaseModel

from ...core import config
from ...core.logging import get_logger
from ..market_structure import Swing

log = get_logger("engines.ict")


class ICTResult(BaseModel):
    symbol: str
    premium_discount: Literal["Premium", "Discount", "Equilibrium"]
    equilibrium: float
    ote: bool                        # price inside the 0.62–0.79 retracement
    ote_zone: tuple[float, float] | None = None
    kill_zone: str = ""              # asian | london | new_york | ln_ny_overlap | ""
    ict_score: int
    quality: str


def _grade(score: int) -> str:
    return ("A+" if score >= 90 else "A" if score >= 80 else "B" if score >= 65
            else "C" if score >= 50 else "D")


def _in_window(t: time, start: str, end: str) -> bool:
    s = time.fromisoformat(start)
    e = time.fromisoformat(end)
    return (s <= t < e) if s <= e else (t >= s or t < e)   # handles wrap past midnight


class ICTEngine:
    def __init__(self) -> None:
        cfg = config.engine("ict")
        zone = cfg.get("ote_zone", {"min": 0.62, "max": 0.79})
        self.ote_min: float = float(zone["min"])
        self.ote_max: float = float(zone["max"])
        self.min_score: int = int(cfg.get("minimum_ict_score", 80))
        self.kill_zones: dict = config.load("sessions").get("kill_zones", {})

    def kill_zone(self, ts: datetime) -> str:
        t = ts.astimezone(timezone.utc).time()
        for name, win in self.kill_zones.items():
            if _in_window(t, win["start"], win["end"]):
                return name
        return ""

    def analyze(self, symbol: str, df: pd.DataFrame, swings: list[Swing],
                trend_bullish: bool, ts: datetime | None = None) -> ICTResult:
        highs = [s.price for s in swings if s.kind == "high"]
        lows = [s.price for s in swings if s.kind == "low"]
        swing_high = max(highs) if highs else float(df["high"].max())
        swing_low = min(lows) if lows else float(df["low"].min())
        rng = swing_high - swing_low or 1e-9
        eq = (swing_high + swing_low) / 2
        close = float(df["close"].iloc[-1])

        pd_zone: Literal["Premium", "Discount", "Equilibrium"] = (
            "Premium" if close > eq + 0.05 * rng else
            "Discount" if close < eq - 0.05 * rng else "Equilibrium")

        # OTE: for a long, retracement into 62–79% of the up-leg (measured from the
        # low); for a short, from the high. Depth measured toward the origin.
        if trend_bullish:
            lo = swing_high - self.ote_max * rng
            hi = swing_high - self.ote_min * rng
        else:
            lo = swing_low + self.ote_min * rng
            hi = swing_low + self.ote_max * rng
        ote_lo, ote_hi = min(lo, hi), max(lo, hi)
        in_ote = ote_lo <= close <= ote_hi

        kz = self.kill_zone(ts) if ts else ""
        score = self._score(pd_zone, trend_bullish, in_ote, kz)
        return ICTResult(
            symbol=symbol, premium_discount=pd_zone, equilibrium=round(eq, 6),
            ote=in_ote, ote_zone=(round(ote_lo, 6), round(ote_hi, 6)),
            kill_zone=kz, ict_score=score, quality=_grade(score))

    def _score(self, pd_zone, trend_bullish, in_ote, kz) -> int:
        score = 30.0
        # discount for longs / premium for shorts is the textbook location
        if (trend_bullish and pd_zone == "Discount") or \
           (not trend_bullish and pd_zone == "Premium"):
            score += 30
        elif pd_zone == "Equilibrium":
            score += 10
        if in_ote:
            score += 25
        if kz:
            score += 15
        return max(0, min(100, round(score)))

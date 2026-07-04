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
    judas_swing: bool = False        # doc 14 §9 — session-open liquidity grab
    amd_phase: Literal["Accumulation", "Manipulation", "Distribution", ""] = ""
    smt_divergence: bool = False     # doc 14 §11 — correlated-asset divergence
    breaker_block: bool = False      # doc 14 §12
    mitigation_block: bool = False   # doc 14 §13
    ict_score: int
    quality: str
    confidence: int = 0              # doc 14 §4 — calibrated 0–100


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
                trend_bullish: bool, ts: datetime | None = None,
                peer_df: pd.DataFrame | None = None) -> ICTResult:
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
        judas = self._judas_swing(df, swing_high, swing_low, kz)
        amd = self._amd_phase(df, rng)
        smt = self._smt_divergence(df, peer_df) if peer_df is not None else False

        score = self._score(pd_zone, trend_bullish, in_ote, kz, judas, smt)
        return ICTResult(
            symbol=symbol, premium_discount=pd_zone, equilibrium=round(eq, 6),
            ote=in_ote, ote_zone=(round(ote_lo, 6), round(ote_hi, 6)),
            kill_zone=kz, judas_swing=judas, amd_phase=amd, smt_divergence=smt,
            ict_score=score, quality=_grade(score), confidence=score)

    # ── Sub-concept detectors (doc 14 §9–11) ──────────────────────────────
    def _judas_swing(self, df: pd.DataFrame, swing_high: float, swing_low: float,
                     kill_zone: str) -> bool:
        """A false move near session open that sweeps liquidity then reverses:
        the last bar wicks beyond a swing extreme but closes back inside."""
        if not kill_zone:
            return False
        last = df.iloc[-1]
        swept_high = last["high"] > swing_high and last["close"] < swing_high
        swept_low = last["low"] < swing_low and last["close"] > swing_low
        return bool(swept_high or swept_low)

    def _amd_phase(self, df: pd.DataFrame,
                   rng: float) -> Literal["Accumulation", "Manipulation", "Distribution", ""]:
        """Coarse AMD read from recent range compression vs expansion (doc 14 §10)."""
        if len(df) < 20:
            return ""
        recent_rng = float(df["high"].tail(10).max() - df["low"].tail(10).min())
        prior_rng = float(df["high"].iloc[-20:-10].max() - df["low"].iloc[-20:-10].min())
        if prior_rng <= 0:
            return ""
        ratio = recent_rng / prior_rng
        if ratio < 0.7:
            return "Accumulation"        # range contracting
        if ratio > 1.4:
            return "Distribution"        # range expanding into targets
        return "Manipulation"

    def _smt_divergence(self, df: pd.DataFrame, peer: pd.DataFrame) -> bool:
        """SMT: one asset makes a higher high while the correlated one fails
        (or the mirror on lows). Compares the last two swings' extremes."""
        n = min(len(df), len(peer))
        if n < 6:
            return False
        a_hh = df["high"].iloc[-1] > df["high"].iloc[-6:-1].max()
        p_hh = peer["high"].iloc[-1] > peer["high"].iloc[-6:-1].max()
        a_ll = df["low"].iloc[-1] < df["low"].iloc[-6:-1].min()
        p_ll = peer["low"].iloc[-1] < peer["low"].iloc[-6:-1].min()
        return bool(a_hh != p_hh or a_ll != p_ll)

    def _score(self, pd_zone, trend_bullish, in_ote, kz, judas=False, smt=False) -> int:
        score = 25.0
        # discount for longs / premium for shorts is the textbook location
        if (trend_bullish and pd_zone == "Discount") or \
           (not trend_bullish and pd_zone == "Premium"):
            score += 25
        elif pd_zone == "Equilibrium":
            score += 8
        if in_ote:
            score += 22
        if kz:
            score += 13
        if judas:
            score += 8
        if smt:
            score += 7
        return max(0, min(100, round(score)))

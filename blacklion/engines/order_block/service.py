"""Order Block Engine (SRS doc 12).

An Order Block is the last opposing candle before a significant institutional
displacement. Bullish OB = last bearish candle before a bullish displacement
(confirmed by a later BOS); bearish OB is the mirror.

Detects, validates, scores freshness/mitigation, tracks the lifecycle. Supplies
validated OBs to the Rule Engine; never executes trades (doc 12 §1).
"""
from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel

from ...core import config
from ...core.events import bus
from ...core.logging import get_logger

log = get_logger("engines.order_block")


class OrderBlock(BaseModel):
    type: Literal["bullish", "bearish"]
    index: int
    price_low: float
    price_high: float
    fresh: bool
    mitigated: bool
    score: int
    quality: str

    def contains(self, price: float) -> bool:
        return self.price_low <= price <= self.price_high


class OrderBlockResult(BaseModel):
    symbol: str
    active: list[OrderBlock] = []
    best: OrderBlock | None = None


def _grade(score: int) -> str:
    return ("A+" if score >= 90 else "A" if score >= 80 else "B" if score >= 65
            else "C" if score >= 50 else "D")


class OrderBlockEngine:
    def __init__(self) -> None:
        cfg = config.engine("order_block")
        self.min_disp_atr: float = float(cfg.get("minimum_displacement_atr", 1.5))
        self.min_score: int = int(cfg.get("minimum_score", 75))
        self.mitig_pct: float = float(cfg.get("mitigation_threshold_pct", 50)) / 100

    def analyze(self, symbol: str, df: pd.DataFrame) -> OrderBlockResult:
        atr = float(df["atr"].iloc[-1]) if "atr" in df and df["atr"].iloc[-1] > 0 else \
            float((df["high"] - df["low"]).tail(14).mean())
        body_avg = float((df["close"] - df["open"]).abs().tail(20).mean()) or atr
        o, high, low, c = (df["open"].values, df["high"].values,
                           df["low"].values, df["close"].values)
        n = len(df)
        blocks: list[OrderBlock] = []

        # scan for displacement candles; the opposing candle just before is the OB
        for i in range(2, n - 1):
            body = abs(c[i] - o[i])
            if body < self.min_disp_atr * body_avg:
                continue
            displacement_up = c[i] > o[i]
            ob_idx = i - 1
            # OB candle must oppose the displacement direction
            if displacement_up and c[ob_idx] < o[ob_idx]:
                ob_type: Literal["bullish", "bearish"] = "bullish"
                lo, hi = float(low[ob_idx]), float(high[ob_idx])
            elif not displacement_up and c[ob_idx] > o[ob_idx]:
                ob_type = "bearish"
                lo, hi = float(low[ob_idx]), float(high[ob_idx])
            else:
                continue

            # BOS confirmation after displacement (doc 12 §6): price extended past
            # the swing the displacement broke
            future_hi = float(high[i + 1:].max()) if i + 1 < n else c[i]
            future_lo = float(low[i + 1:].min()) if i + 1 < n else c[i]

            # mitigation: has price returned into the zone since?
            after_lo = low[i + 1:]
            after_hi = high[i + 1:]
            touched = False
            if len(after_lo):
                touched = bool(((after_lo <= hi) & (after_hi >= lo)).any())
            fresh = not touched

            score = self._score(body, body_avg, ob_type, displacement_up,
                                 future_hi, future_lo, hi, lo, fresh)
            if score < self.min_score:
                continue
            blocks.append(OrderBlock(
                type=ob_type, index=ob_idx, price_low=lo, price_high=hi,
                fresh=fresh, mitigated=touched, score=score, quality=_grade(score)))

        # keep most recent, dedup overlapping zones, rank fresh + score
        blocks = self._dedup(blocks)
        best = max(blocks, key=lambda b: (b.fresh, b.score), default=None)
        for b in blocks:
            bus.publish("BullishOrderBlockDetected" if b.type == "bullish"
                        else "BearishOrderBlockDetected",
                        symbol=symbol, zone=[b.price_low, b.price_high])
        return OrderBlockResult(symbol=symbol, active=blocks[-8:], best=best)

    @staticmethod
    def _dedup(blocks: list[OrderBlock]) -> list[OrderBlock]:
        out: list[OrderBlock] = []
        for b in sorted(blocks, key=lambda x: x.index):
            if out and out[-1].type == b.type and \
               out[-1].price_low <= b.price_high and b.price_low <= out[-1].price_high:
                if b.score > out[-1].score:
                    out[-1] = b
            else:
                out.append(b)
        return out

    def _score(self, body, body_avg, ob_type, disp_up, fut_hi, fut_lo, hi, lo, fresh) -> int:
        score = 40.0
        score += min(25, 15 * (body / body_avg))                 # displacement strength
        # follow-through past the OB (proxy for BOS quality)
        if disp_up and fut_hi > hi:
            score += min(20, 20 * (fut_hi - hi) / (hi - lo + 1e-9) / 3)
        elif not disp_up and fut_lo < lo:
            score += min(20, 20 * (lo - fut_lo) / (hi - lo + 1e-9) / 3)
        score += 15 if fresh else 0
        return max(0, min(100, round(score)))

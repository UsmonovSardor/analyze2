"""Liquidity Engine (SRS doc 11) — Smart Money Concepts liquidity analysis.

Detects Equal Highs/Lows, Buy-Side / Sell-Side Liquidity pools, liquidity
sweeps and stop hunts. Provides liquidity context to the Rule Engine; never
generates buy/sell signals (doc 11 §1).

Consumes the Market Structure swings so the pipeline sees the same structure
the Rule Engine scores.
"""
from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel

from ...core import config
from ...core.events import bus
from ...core.logging import get_logger
from ..market_structure import Swing

log = get_logger("engines.liquidity")


class LiquidityPool(BaseModel):
    side: Literal["buy", "sell"]     # BSL rests above highs, SSL below lows
    price: float
    touches: int                     # equal highs/lows forming the pool
    swept: bool = False


class LiquidityResult(BaseModel):
    symbol: str
    buy_side_liquidity: bool
    sell_side_liquidity: bool
    liquidity_swept: bool
    sweep_direction: Literal["bullish", "bearish", ""] = ""
    stop_hunt: bool = False
    nearest_pool: float | None = None
    distance: float | None = None    # to nearest pool, in ATR units
    liquidity_score: int
    quality: str
    pools: list[LiquidityPool] = []


def _grade(score: int) -> str:
    return ("A+" if score >= 90 else "A" if score >= 80 else "B" if score >= 65
            else "C" if score >= 50 else "D")


class LiquidityEngine:
    def __init__(self) -> None:
        cfg = config.engine("liquidity")
        self.tol_atr: float = float(cfg.get("equal_tolerance_atr", 0.1))
        self.min_touches: int = int(cfg.get("minimum_touches", 2))
        self.min_score: int = int(cfg.get("minimum_liquidity_score", 70))
        self.stop_hunt_filter: bool = bool(cfg.get("enable_stop_hunt_filter", True))

    def _cluster(self, swings: list[Swing], kind: str, atr: float) -> list[LiquidityPool]:
        """Group swings of one kind whose prices sit within tol into a pool
        (Equal Highs / Equal Lows, doc 11 §8–9)."""
        pts = sorted((s.price for s in swings if s.kind == kind))
        if not pts:
            return []
        tol = max(self.tol_atr * atr, 1e-9)
        pools: list[LiquidityPool] = []
        group = [pts[0]]
        side: Literal["buy", "sell"] = "buy" if kind == "high" else "sell"
        for p in pts[1:]:
            if p - group[-1] <= tol:
                group.append(p)
            else:
                if len(group) >= self.min_touches:
                    pools.append(LiquidityPool(side=side, price=sum(group) / len(group),
                                               touches=len(group)))
                group = [p]
        if len(group) >= self.min_touches:
            pools.append(LiquidityPool(side=side, price=sum(group) / len(group),
                                       touches=len(group)))
        return pools

    def analyze(self, symbol: str, df: pd.DataFrame, swings: list[Swing]) -> LiquidityResult:
        atr = float(df["atr"].iloc[-1]) if "atr" in df and df["atr"].iloc[-1] > 0 else \
            float((df["high"] - df["low"]).tail(14).mean())
        close = float(df["close"].iloc[-1])
        last = df.iloc[-1]

        bsl = self._cluster(swings, "high", atr)
        ssl = self._cluster(swings, "low", atr)
        pools = bsl + ssl

        # Sweep detection (doc 11 §10): wick pierces a pool, body closes back.
        swept, sweep_dir, stop_hunt = False, "", False
        for pool in pools:
            if pool.side == "sell" and last["low"] < pool.price <= last["close"]:
                pool.swept = swept = True
                sweep_dir = "bullish"          # swept SSL then rejected up
            elif pool.side == "buy" and last["high"] > pool.price >= last["close"]:
                pool.swept = swept = True
                sweep_dir = "bearish"          # swept BSL then rejected down
        if swept and self.stop_hunt_filter:
            rng = float(last["high"] - last["low"])
            body = abs(float(last["close"] - last["open"]))
            vol_ok = ("volume" not in df or last["volume"] >=
                      0.9 * df["volume"].tail(20).mean())
            stop_hunt = rng > 0.8 * atr and body / (rng or 1) >= 0.4 and vol_ok

        nearest = min(pools, key=lambda p: abs(p.price - close), default=None)
        dist = abs(nearest.price - close) / atr if nearest and atr else None
        score = self._score(bsl, ssl, swept, stop_hunt, dist)

        result = LiquidityResult(
            symbol=symbol,
            buy_side_liquidity=bool(bsl),
            sell_side_liquidity=bool(ssl),
            liquidity_swept=swept, sweep_direction=sweep_dir, stop_hunt=stop_hunt,
            nearest_pool=nearest.price if nearest else None,
            distance=round(dist, 3) if dist is not None else None,
            liquidity_score=score, quality=_grade(score),
            pools=pools,
        )
        if swept:
            bus.publish("LiquiditySweep", symbol=symbol, direction=sweep_dir)
        if stop_hunt:
            bus.publish("StopHuntConfirmed", symbol=symbol, direction=sweep_dir)
        return result

    def _score(self, bsl, ssl, swept, stop_hunt, dist) -> int:
        score = 0.0
        pools = bsl + ssl
        if pools:
            score += min(30, 10 * max(p.touches for p in pools))     # pool strength
            score += min(15, 5 * len(pools))                         # pool count
        if swept:
            score += 20
        if stop_hunt:
            score += 20
        if dist is not None:
            score += max(0.0, 15 * (1 - min(dist, 1.5) / 1.5))       # closer = better
        return max(0, min(100, round(score)))

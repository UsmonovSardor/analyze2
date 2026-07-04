"""Market Structure Engine (SRS doc 10).

Objective price-action structure: swing highs/lows, HH/HL/LH/LL classification,
Break of Structure (BOS), Change of Character (CHOCH), trend state and strength.
No buy/sell signal is generated here — output feeds the Rule Engine.

Deterministic: same candles in → same structure out (SRS doc 01 §10).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

import pandas as pd
from pydantic import BaseModel

from ...core import config
from ...core.events import bus
from ...core.logging import get_logger

log = get_logger("engines.market_structure")


class Trend(StrEnum):
    STRONG_BULLISH = "Strong Bullish"
    BULLISH = "Bullish"
    WEAK_BULLISH = "Weak Bullish"
    SIDEWAYS = "Sideways"
    WEAK_BEARISH = "Weak Bearish"
    BEARISH = "Bearish"
    STRONG_BEARISH = "Strong Bearish"

    @property
    def bullish(self) -> bool:
        return self in (Trend.STRONG_BULLISH, Trend.BULLISH, Trend.WEAK_BULLISH)

    @property
    def bearish(self) -> bool:
        return self in (Trend.STRONG_BEARISH, Trend.BEARISH, Trend.WEAK_BEARISH)


@dataclass(frozen=True)
class Swing:
    index: int                       # bar index in the analyzed frame
    price: float
    kind: Literal["high", "low"]
    label: str = ""                  # HH / HL / LH / LL (set during classification)


class StructureResult(BaseModel):
    symbol: str
    trend: Trend
    structure: str                   # e.g. "HH-HL"
    bos: bool
    bos_direction: Literal["bullish", "bearish", ""] = ""
    choch: bool
    choch_direction: Literal["bullish", "bearish", ""] = ""
    strength: int                    # 0–100
    quality: str                     # A+ / A / B / C / D
    confidence: int                  # doc 10 §4 — calibrated 0–100
    swings: list[dict] = []
    last_swing_high: float | None = None
    last_swing_low: float | None = None


def _grade(score: int) -> str:
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"


class MarketStructureEngine:
    """df columns required: open, high, low, close, volume, atr (float)."""

    def __init__(self) -> None:
        cfg = config.engine("market_structure")
        self.window: int = int(cfg.get("swing_window", 5))
        self.min_break_atr: float = float(cfg.get("minimum_break_atr", 0.2))
        # how many recent swings count as a "recent" structural break (regime flag)
        self.break_lookback_swings: int = int(cfg.get("break_lookback_swings", 2))

    # ── Swing detection (doc 10 §6) ────────────────────────────────────────
    def detect_swings(self, df: pd.DataFrame) -> list[Swing]:
        w = self.window
        highs, lows = df["high"].values, df["low"].values
        swings: list[Swing] = []
        for i in range(w, len(df) - w):
            seg_h = highs[i - w : i + w + 1]
            seg_l = lows[i - w : i + w + 1]
            # plateau-tolerant: the FIRST bar of an equal-extreme run is the swing
            if highs[i] == seg_h.max() and int(seg_h.argmax()) == w:
                swings.append(Swing(index=i, price=float(highs[i]), kind="high"))
            elif lows[i] == seg_l.min() and int(seg_l.argmin()) == w:
                swings.append(Swing(index=i, price=float(lows[i]), kind="low"))
        return swings

    # ── HH/HL/LH/LL classification (doc 10 §7) ────────────────────────────
    @staticmethod
    def classify(swings: list[Swing]) -> list[Swing]:
        labeled: list[Swing] = []
        prev_high: Swing | None = None
        prev_low: Swing | None = None
        for s in swings:
            if s.kind == "high":
                label = "HH" if (prev_high and s.price > prev_high.price) else (
                    "LH" if prev_high else "H")
                prev_high = s
            else:
                label = "HL" if (prev_low and s.price > prev_low.price) else (
                    "LL" if prev_low else "L")
                prev_low = s
            labeled.append(Swing(index=s.index, price=s.price, kind=s.kind, label=label))
        return labeled

    # ── Trend (doc 10 §10) ────────────────────────────────────────────────
    @staticmethod
    def _trend_from_labels(labels: list[str]) -> Trend:
        recent = [lb for lb in labels if lb in ("HH", "HL", "LH", "LL")][-6:]
        if not recent:
            return Trend.SIDEWAYS
        bull = sum(1 for lb in recent if lb in ("HH", "HL"))
        bear = sum(1 for lb in recent if lb in ("LH", "LL"))
        total = len(recent)
        if bull == total and total >= 4:
            return Trend.STRONG_BULLISH
        if bear == total and total >= 4:
            return Trend.STRONG_BEARISH
        if bull / total >= 0.75:
            return Trend.BULLISH
        if bear / total >= 0.75:
            return Trend.BEARISH
        if bull / total >= 0.6:
            return Trend.WEAK_BULLISH
        if bear / total >= 0.6:
            return Trend.WEAK_BEARISH
        return Trend.SIDEWAYS

    # ── Main analysis ─────────────────────────────────────────────────────
    def analyze(self, symbol: str, df: pd.DataFrame) -> StructureResult:
        swings = self.classify(self.detect_swings(df))
        labels = [s.label for s in swings]
        trend = self._trend_from_labels(labels)

        close = float(df["close"].iloc[-1])
        atr = float(df["atr"].iloc[-1]) if "atr" in df else 0.0
        min_break = self.min_break_atr * atr

        sw_highs = [s for s in swings if s.kind == "high"]
        sw_lows = [s for s in swings if s.kind == "low"]
        last_high = sw_highs[-1] if sw_highs else None
        last_low = sw_lows[-1] if sw_lows else None

        # Two kinds of break:
        #  • immediate — this bar's close pierced the last swing (a fresh event)
        #  • recent    — a HH/LL formed in the last few swings (a REGIME flag that
        #    stays valid through the pullback where SMC entries actually happen)
        recent = [s.label for s in swings][-self.break_lookback_swings * 2:]
        imm_bull = last_high is not None and close > last_high.price + min_break
        imm_bear = last_low is not None and close < last_low.price - min_break
        with_trend_bull = imm_bull or "HH" in recent
        with_trend_bear = imm_bear or "LL" in recent

        # CHOCH is the FIRST fresh break against the prevailing trend — it takes
        # priority over a continuation BOS. BOS is the recent with-trend structure.
        bos, bos_dir = False, ""
        choch, choch_dir = False, ""
        if trend.bullish:
            if imm_bear:
                choch, choch_dir = True, "bearish"
            elif with_trend_bull:
                bos, bos_dir = True, "bullish"
        elif trend.bearish:
            if imm_bull:
                choch, choch_dir = True, "bullish"
            elif with_trend_bear:
                bos, bos_dir = True, "bearish"
        else:                                    # transition: a fresh break = CHOCH
            if imm_bull or "HH" in recent:
                choch, choch_dir = True, "bullish"
            elif imm_bear or "LL" in recent:
                choch, choch_dir = True, "bearish"

        strength = self._strength(labels, trend, bos, df)
        result = StructureResult(
            symbol=symbol,
            trend=trend,
            structure="-".join(labels[-2:]) if len(labels) >= 2 else (labels[-1] if labels else ""),
            bos=bos, bos_direction=bos_dir,
            choch=choch, choch_direction=choch_dir,
            strength=strength, quality=_grade(strength),
            confidence=strength,     # structure strength is the confidence proxy
            swings=[{"index": s.index, "price": s.price, "kind": s.kind, "label": s.label}
                    for s in swings[-10:]],
            last_swing_high=last_high.price if last_high else None,
            last_swing_low=last_low.price if last_low else None,
        )

        if bos:
            bus.publish("BullishBOS" if bos_dir == "bullish" else "BearishBOS",
                        symbol=symbol, price=close)
        if choch:
            bus.publish("BullishCHOCH" if choch_dir == "bullish" else "BearishCHOCH",
                        symbol=symbol, price=close)
        return result

    # ── Strength score 0–100 (doc 10 §12) ─────────────────────────────────
    @staticmethod
    def _strength(labels: list[str], trend: Trend, bos: bool, df: pd.DataFrame) -> int:
        recent = [lb for lb in labels if lb in ("HH", "HL", "LH", "LL")][-6:]
        if not recent:
            return 20
        dominant = ("HH", "HL") if not trend.bearish else ("LH", "LL")
        consistency = sum(1 for lb in recent if lb in dominant) / len(recent)   # swing quality
        score = 30 * consistency
        score += 20 if bos else 0
        # momentum: last close vs close N bars ago, scaled by ATR
        n = min(20, len(df) - 1)
        atr = float(df["atr"].iloc[-1]) if "atr" in df and df["atr"].iloc[-1] > 0 else None
        if atr:
            move = abs(float(df["close"].iloc[-1]) - float(df["close"].iloc[-1 - n])) / (atr * n)
            score += min(25.0, move * 50)
        if trend in (Trend.STRONG_BULLISH, Trend.STRONG_BEARISH):
            score += 25
        elif trend in (Trend.BULLISH, Trend.BEARISH):
            score += 15
        elif trend in (Trend.WEAK_BULLISH, Trend.WEAK_BEARISH):
            score += 8
        return max(0, min(100, round(score)))

"""Rule Engine (SRS doc 15) — deterministic decision core.

Aggregates every analytical engine into ONE decision: BUY / SELL / NO TRADE.
Applies mandatory conditions (doc 15 §6), weighted confluence scoring (§10) and
anchors entry/SL/TP to real levels — never invents prices (doc 01 §10).

The AI Decision + Probability engines (docs 16–17) refine this later; they can
only make the system MORE selective, never override a NO TRADE into a trade.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from ...core import config
from ...core.events import bus
from ...core.logging import get_logger
from ..fvg import FVGResult
from ..ict import ICTResult
from ..liquidity import LiquidityResult
from ..market_structure import StructureResult
from ..order_block import OrderBlockResult

log = get_logger("engines.rule_engine")

Direction = Literal["BUY", "SELL", "NO TRADE"]


class Signal(BaseModel):
    symbol: str
    direction: Literal["BUY", "SELL"]
    entry: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    rr: float                        # entry→tp2 in R
    confidence: int
    confluence_score: int
    reasons: list[str]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RuleDecision(BaseModel):
    symbol: str
    decision: Direction
    confluence_score: int
    confidence: int
    reasons: list[str] = []
    rejected: list[str] = []
    signal: Signal | None = None


class RuleEngine:
    def __init__(self) -> None:
        cfg = config.engine("rule_engine")
        self.min_confluence: int = int(cfg.get("minimum_confluence_score", 80))
        self.min_confidence: int = int(cfg.get("minimum_confidence", 85))
        self.require_htf: bool = bool(cfg.get("require_htf_alignment", True))
        self.allow_counter: bool = bool(cfg.get("allow_countertrend", False))
        self.w: dict = cfg["weights"]
        self.risk = config.load("risk")

    def evaluate(self, symbol: str, df: pd.DataFrame,
                 structure: StructureResult, liquidity: LiquidityResult,
                 order_block: OrderBlockResult, fvg: FVGResult, ict: ICTResult,
                 htf_bullish: bool | None = None) -> RuleDecision:
        reasons: list[str] = []
        rejected: list[str] = []

        bull = structure.trend.bullish
        bear = structure.trend.bearish
        direction: Direction = "BUY" if bull else "SELL" if bear else "NO TRADE"

        # ── Mandatory conditions (doc 15 §6) ──────────────────────────────
        if direction == "NO TRADE":
            rejected.append("no directional structure (sideways)")
        if not (structure.bos or structure.choch):
            rejected.append("no BOS/CHOCH confirmation")
        if self.require_htf and htf_bullish is not None and direction != "NO TRADE":
            if (direction == "BUY") != htf_bullish:
                rejected.append("HTF trend conflicts with entry")
        if not self.allow_counter and direction != "NO TRADE":
            if (direction == "BUY" and bear) or (direction == "SELL" and bull):
                rejected.append("counter-trend")

        ob = order_block.best
        ob_aligned = ob is not None and (
            (direction == "BUY" and ob.type == "bullish") or
            (direction == "SELL" and ob.type == "bearish"))
        fvg_aligned = fvg.nearest is not None and (
            (direction == "BUY" and fvg.nearest.type == "bullish") or
            (direction == "SELL" and fvg.nearest.type == "bearish"))
        if not (ob_aligned or fvg_aligned):
            rejected.append("no aligned Order Block or FVG")

        # location: longs from discount, shorts from premium (doc 15 §7–8)
        if direction == "BUY" and ict.premium_discount == "Premium":
            rejected.append("long from premium zone")
        if direction == "SELL" and ict.premium_discount == "Discount":
            rejected.append("short from discount zone")

        confluence = self._confluence(direction, structure, liquidity,
                                      order_block, fvg, ict, ob_aligned, fvg_aligned,
                                      vol_factor=self._vol_factor(df))

        if rejected or confluence < self.min_confluence:
            if confluence < self.min_confluence and not rejected:
                rejected.append(f"confluence {confluence} < {self.min_confluence}")
            bus.publish("SignalRejected", symbol=symbol, reasons=rejected)
            return RuleDecision(symbol=symbol, decision="NO TRADE",
                                confluence_score=confluence, confidence=0,
                                rejected=rejected)

        # ── Build the signal — anchor levels to structure ─────────────────
        reasons = self._reasons(symbol, df, direction, structure, liquidity,
                                ob, fvg, ict)
        signal = self._build_signal(symbol, df, direction, structure, ob, fvg, confluence)
        if signal is None:
            rejected.append("risk/reward below minimum after level anchoring")
            return RuleDecision(symbol=symbol, decision="NO TRADE",
                                confluence_score=confluence, confidence=0,
                                rejected=rejected)

        signal.reasons = reasons
        bus.publish("SignalGenerated", symbol=symbol, direction=direction,
                    confidence=signal.confidence)
        return RuleDecision(symbol=symbol, decision=direction,
                            confluence_score=confluence, confidence=signal.confidence,
                            reasons=reasons, signal=signal)

    # ── Weighted confluence (doc 15 §10) ──────────────────────────────────
    def _confluence(self, direction, structure, liquidity, order_block, fvg,
                    ict, ob_aligned, fvg_aligned, vol_factor: float = 0.7) -> int:
        w = self.w
        score = 0.0
        score += w["market_structure"] * structure.strength / 100
        score += w["liquidity"] * liquidity.liquidity_score / 100

        # Zone = the institutional entry area. The mandatory gate already requires
        # an aligned OB OR FVG, so scoring them SEPARATELY structurally caps the
        # score (the missing one contributes 0). Credit the BEST aligned zone, with
        # a small bonus when BOTH confirm — a setup isn't "worse" for lacking one.
        ob_s = order_block.best.score if ob_aligned else 0
        fvg_s = fvg.nearest.score if fvg_aligned else 0
        zone = max(ob_s, fvg_s) / 100
        if ob_aligned and fvg_aligned:
            zone = min(1.0, zone + 0.1)
        score += w["zone"] * zone

        score += w["ict"] * ict.ict_score / 100
        trend_factor = 1.0 if structure.trend.name.startswith("STRONG") else \
            0.7 if direction != "NO TRADE" else 0.3
        score += w["trend"] * trend_factor
        score += w["volatility"] * vol_factor
        score += w["session"] * (1.0 if ict.kill_zone else 0.4)
        return max(0, min(100, round(score)))

    @staticmethod
    def _vol_factor(df: pd.DataFrame) -> float:
        """Healthy volatility scores ~1.0; dead or chaotic markets score lower.
        Uses current ATR vs its own recent average (doc 09 volatility features)."""
        if "atr" not in df or len(df) < 20:
            return 0.7
        atr = float(df["atr"].iloc[-1])
        avg = float(df["atr"].tail(50).mean()) or atr
        if avg <= 0:
            return 0.7
        ratio = atr / avg
        # best band 0.8–1.5× average; taper outside it
        if 0.8 <= ratio <= 1.5:
            return 1.0
        if ratio < 0.8:
            return max(0.4, ratio / 0.8)
        return max(0.4, 1.5 / ratio)

    def _confidence(self, confluence: int, structure: StructureResult) -> int:
        # confidence blends confluence with structure quality (doc 15 §11)
        base = 0.7 * confluence + 0.3 * structure.strength
        return max(0, min(100, round(base)))

    # Uzbek display names (professional caption; technical terms stay latin)
    _TREND_UZ = {
        "Strong Bullish": "Kuchli ko'tarilish", "Bullish": "Ko'tarilish",
        "Weak Bullish": "Zaif ko'tarilish", "Sideways": "Yonlama",
        "Weak Bearish": "Zaif tushish", "Bearish": "Tushish",
        "Strong Bearish": "Kuchli tushish",
    }
    _KZ_UZ = {"asian": "Osiyo", "london": "London", "new_york": "Nyu-York",
              "ln_ny_overlap": "London–NY kesishuvi"}

    def _reasons(self, symbol, df, direction, structure, liquidity,
                 ob, fvg, ict) -> list[str]:
        """Data-valued Uzbek reasons — every line carries the actual numbers the
        engines saw, so no two signals read alike (user demand: professional,
        specific reasoning instead of the same canned five lines)."""
        digits = int(config.load("symbols")["symbols"]
                     .get(symbol, {}).get("digits", 5))

        def p(x: float | None) -> str:
            return "?" if x is None else f"{x:.{digits}f}".rstrip("0").rstrip(".")

        r: list[str] = []

        # ── structure: trend + strength + break + protective swing ───────
        trend_uz = self._TREND_UZ.get(structure.trend.value, structure.trend.value)
        brk = "CHOCH" if structure.choch else "BOS"
        brk_dir = structure.choch_direction if structure.choch else structure.bos_direction
        swing = structure.last_swing_low if direction == "BUY" else structure.last_swing_high
        r.append(f"{trend_uz} tuzilma {structure.structure} "
                 f"(kuch {structure.strength}/100) · {brk_dir} {brk}"
                 + (f" · himoya swing {p(swing)}" if swing else ""))

        # ── liquidity: what was swept / where the pool sits ───────────────
        if liquidity.liquidity_swept:
            side = "sell-side" if liquidity.sweep_direction == "bullish" else "buy-side"
            hunt = " (stop-hunt)" if liquidity.stop_hunt else ""
            r.append(f"{side} likvidlik supurildi{hunt}"
                     + (f" · pool {p(liquidity.nearest_pool)}"
                        if liquidity.nearest_pool else ""))

        # ── zone: OB / FVG with real price bands + scores ─────────────────
        if ob:
            fresh = " · yangi" if ob.fresh else ""
            r.append(f"{ob.quality} Order Block {p(ob.price_low)}–{p(ob.price_high)} "
                     f"(score {ob.score}){fresh}")
        if fvg.nearest:
            g = fvg.nearest
            r.append(f"{g.quality} FVG {p(g.gap_low)}–{p(g.gap_high)} "
                     f"({g.filled_pct:.0f}% to'ldirilgan)")

        # ── location + session ────────────────────────────────────────────
        loc = (f"{ict.premium_discount} zona (equilibrium {p(ict.equilibrium)})")
        if ict.ote and ict.ote_zone:
            loc += f" · OTE {p(ict.ote_zone[0])}–{p(ict.ote_zone[1])}"
        if ict.kill_zone:
            loc += f" · {self._KZ_UZ.get(ict.kill_zone, ict.kill_zone)} kill zone"
        r.append(loc)

        # ── momentum: RSI turn + EMA stack with values ────────────────────
        if "rsi" in df and len(df) >= 2:
            rsi_now, rsi_prev = float(df["rsi"].iloc[-1]), float(df["rsi"].iloc[-2])
            turn = "ko'tarilmoqda" if rsi_now >= rsi_prev else "pasaymoqda"
            r.append(f"RSI {rsi_prev:.1f}→{rsi_now:.1f} {turn}"
                     + (f" · EMA50 {p(float(df['ema50'].iloc[-1]))} "
                        f"{'>' if float(df['ema50'].iloc[-1]) >= float(df['ema200'].iloc[-1]) else '<'}"
                        f" EMA200 {p(float(df['ema200'].iloc[-1]))}"
                        if "ema50" in df and "ema200" in df else ""))

        # ── volatility health ─────────────────────────────────────────────
        if "atr" in df and len(df) >= 20:
            atr = float(df["atr"].iloc[-1])
            avg = float(df["atr"].tail(50).mean()) or atr
            if avg > 0:
                ratio = atr / avg
                state = ("sog'lom" if 0.8 <= ratio <= 1.5
                         else "past" if ratio < 0.8 else "keskin")
                r.append(f"ATR {p(atr)} — {state} volatillik "
                         f"(o'rtachaning {ratio:.1f}×)")
        return r

    def _build_signal(self, symbol, df, direction, structure, ob, fvg,
                      confluence) -> Signal | None:
        atr = float(df["atr"].iloc[-1]) if "atr" in df and df["atr"].iloc[-1] > 0 else \
            float((df["high"] - df["low"]).tail(14).mean())
        entry = float(df["close"].iloc[-1])
        min_rr = float(self.risk["minimum_rr"])

        # SL beyond the protective structure (OB far edge / recent swing) + ATR buffer
        if direction == "BUY":
            protective = ob.price_low if ob else structure.last_swing_low
            protective = protective if protective is not None else entry - 1.5 * atr
            sl = min(protective, entry - 1.0 * atr) - 0.1 * atr
            if entry - sl <= 0:
                return None
        else:
            protective = ob.price_high if ob else structure.last_swing_high
            protective = protective if protective is not None else entry + 1.5 * atr
            sl = max(protective, entry + 1.0 * atr) + 0.1 * atr
            if sl - entry <= 0:
                return None

        digits = config.load("symbols")["symbols"].get(symbol, {}).get("digits", 5)
        step = 10 ** -digits

        def rnd(x: float) -> float:
            return round(x, digits)

        # Round entry & stop to the instrument tick FIRST, then derive R and every
        # target from those stored values — the risk engine recomputes RR from
        # exactly these, so signal and risk must agree. Round each TP AWAY from
        # entry (distance rounded UP to a whole tick) so a rounding tick can never
        # shrink realized R below the intended multiple and make risk veto our own
        # signal — e.g. a 2.0R TP2 landing at 1.99R after rounding (doc 18 §10).
        e, sl = rnd(entry), rnd(sl)
        r = abs(e - sl)
        if r <= 0:
            return None
        up = direction == "BUY"

        def target(mult: float) -> float:
            dist = math.ceil(mult * r / step) * step
            return rnd(e + dist if up else e - dist)

        tp1, tp2, tp3 = target(1.5), target(min_rr), target(4.0)
        rr = abs(tp2 - e) / r
        if rr < min_rr:
            return None
        return Signal(
            symbol=symbol, direction=direction,  # type: ignore[arg-type]
            entry=e, stop_loss=sl,
            tp1=tp1, tp2=tp2, tp3=tp3, rr=round(rr, 2),
            confidence=self._confidence(confluence, structure),
            confluence_score=confluence, reasons=[])

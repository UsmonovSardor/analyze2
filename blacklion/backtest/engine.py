"""Backtesting Engine (SRS doc 20).

Replays historical candles through the SAME pipeline the live bot uses
(structure → liquidity → OB → FVG → ICT → rule → risk), so the backtest measures
the real strategy, not a re-implementation. Strictly causal — at bar i the
pipeline only ever sees candles up to i (no lookahead).

Trades are simulated forward with the live outcome logic: 40/40/20 partial exits
and stop-to-breakeven after TP1 (same as runtime.check_outcomes), so backtest and
live results are directly comparable.

Honesty note (like the old bot): this is a faithful test of the deterministic
Rule Engine path. The AI/Probability layer only makes the system MORE selective,
so these numbers are a conservative proxy for "is the edge real?", not a promise.
"""
from __future__ import annotations

import pandas as pd
from pydantic import BaseModel

from ..core.logging import get_logger
from ..data.indicators import add_indicators
from ..engines.market_structure import MarketStructureEngine
from ..engines.pipeline import SignalPipeline
from .metrics import Metrics, compute_metrics

log = get_logger("backtest")


class TradeResult(BaseModel):
    symbol: str
    direction: str
    entry_index: int
    result_r: float
    outcome: str                     # tp3 | tp2 | tp1 | breakeven | stopped | timeout
    bars_held: int


class BacktestReport(BaseModel):
    symbol: str
    bars: int
    trades: list[TradeResult]
    metrics: Metrics


class Backtester:
    def __init__(self, htf_ratio: int = 4, warmup: int = 250,
                 cooldown_bars: int = 12, lookforward: int = 120,
                 step: int = 1) -> None:
        self.htf_ratio = htf_ratio       # entry bars per higher-timeframe bar
        self.warmup = warmup
        self.cooldown_bars = cooldown_bars
        self.lookforward = lookforward   # max bars to resolve a trade
        self.step = step                 # sample every k bars (speed knob)
        self.pipeline = SignalPipeline()
        self.structure = MarketStructureEngine()

    def run(self, symbol: str, df: pd.DataFrame) -> BacktestReport:
        """df: entry-TF OHLCV(+atr) frame, oldest first. Returns trades + metrics."""
        if "atr" not in df.columns:
            df = add_indicators(df)
        df = df.reset_index(drop=True)
        n = len(df)
        trades: list[TradeResult] = []
        cooldown = 0

        for i in range(self.warmup, n - 1, self.step):
            if cooldown > 0:
                cooldown -= self.step
                continue
            window = df.iloc[: i + 1]
            htf_bullish = self._htf_trend(symbol, window)
            decision = self.pipeline.run(symbol, window, htf_bullish=htf_bullish)
            if decision.signal is None:
                continue
            result = self._simulate(symbol, df, i, decision.signal)
            if result is not None:
                trades.append(result)
                cooldown = self.cooldown_bars

        report = BacktestReport(
            symbol=symbol, bars=n, trades=trades,
            metrics=compute_metrics([t.result_r for t in trades]))
        log.info("BacktestDone", symbol=symbol, bars=n, trades=len(trades),
                 net_r=report.metrics.net_r, win_rate=report.metrics.win_rate)
        return report

    # ── causal higher-timeframe trend ─────────────────────────────────────
    def _htf_trend(self, symbol: str, window: pd.DataFrame) -> bool:
        ratio = self.htf_ratio
        m = (len(window) // ratio) * ratio
        if m < ratio * 2:
            return True                  # not enough for HTF → don't block
        blocks = window.iloc[:m].reset_index(drop=True)
        grp = blocks.index // ratio
        htf = blocks.groupby(grp).agg(
            {"open": "first", "high": "max", "low": "min",
             "close": "last", "volume": "sum"}).reset_index(drop=True)
        htf = add_indicators(htf)
        return self.structure.analyze(symbol, htf).trend.bullish

    # ── forward trade simulation (matches runtime outcome logic) ──────────
    def _simulate(self, symbol: str, df: pd.DataFrame, i: int, sig) -> TradeResult | None:
        long = sig.direction == "BUY"
        sign = 1.0 if long else -1.0
        e, sl = sig.entry, sig.stop_loss
        tp1, tp2, tp3 = sig.tp1, sig.tp2, sig.tp3
        r = abs(e - sl)
        if r <= 0:
            return None

        status = "open"
        end = min(i + 1 + self.lookforward, len(df))
        for j in range(i + 1, end):
            hi = float(df["high"].iloc[j])
            lo = float(df["low"].iloc[j])
            eff_sl = e if status in ("tp1", "tp2") else sl
            stop_hit = (lo <= eff_sl) if long else (hi >= eff_sl)
            reached = (lambda lvl: hi >= lvl) if long else (lambda lvl: lo <= lvl)

            if stop_hit:
                if status == "open":
                    return self._res(symbol, sig, i, -1.0, "stopped", j - i)
                parts = 0.4 * sign * (tp1 - e) / r
                if status == "tp2":
                    parts += 0.4 * sign * (tp2 - e) / r
                rem = {"tp1": 0.6, "tp2": 0.2}[status]
                return self._res(symbol, sig, i, round(parts + rem * sign * (eff_sl - e) / r, 3),
                                 "breakeven", j - i)
            if reached(tp3) and status == "tp2":
                total = sign * (0.4 * (tp1 - e) + 0.4 * (tp2 - e) + 0.2 * (tp3 - e)) / r
                return self._res(symbol, sig, i, round(total, 3), "tp3", j - i)
            if reached(tp2) and status == "tp1":
                status = "tp2"
            elif reached(tp1) and status == "open":
                status = "tp1"

        # timed out — mark to last close
        last = float(df["close"].iloc[end - 1])
        return self._res(symbol, sig, i, round(sign * (last - e) / r, 3),
                         "timeout", end - 1 - i)

    @staticmethod
    def _res(symbol, sig, i, result_r, outcome, held) -> TradeResult:
        return TradeResult(symbol=symbol, direction=sig.direction, entry_index=i,
                           result_r=result_r, outcome=outcome, bars_held=held)

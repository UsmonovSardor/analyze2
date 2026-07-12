"""Setup A — Trend Pullback (docs/strategies/strategy.md §Setup A).

Nison reversal + Brooks High-2 pullback + Livermore trend following, mirrored for
shorts. ALL entry conditions must hold:
  1. price pulled into the EMA50 zone (±ema_zone_atr×ATR), retrace 25–75% of the
     prior swing (>75% = trend failure, Brooks rule)
  2. RSI reset past the band within rsi_lookback bars AND turning back
  3. a named candle confirmation on the signal bar
  4. no absorption wick against the trade
  5. scorecard total ≥ min_score
"""
from __future__ import annotations

from . import candles, scorecard
from .base import DetectorContext, StrategyMatch


class TrendPullback:
    code = "A"
    name = "Trend Pullback"

    def detect(self, ctx: DetectorContext) -> StrategyMatch | None:
        cfg = ctx.cfg
        df = ctx.df
        need = {"close", "ema50", "atr", "rsi"}
        if not need <= set(df.columns) or len(df) < 30:
            return None

        if ctx.regime in ("strong_bull", "bull_pullback"):
            direction = "BUY"
        elif ctx.regime in ("strong_bear", "bear_rally"):
            direction = "SELL"
        else:
            return None                              # pullbacks need a trend
        up = direction == "BUY"

        close = float(df["close"].iloc[-1])
        ema50 = float(df["ema50"].iloc[-1])
        atr = float(df["atr"].iloc[-1])
        if atr <= 0:
            return None

        # 1 — pullback INTO the EMA50 zone…
        if abs(close - ema50) > float(cfg.get("ema_zone_atr", 1.0)) * atr:
            return None
        # …and 25–75% retrace of the prior swing (needs both swings known)
        hi, lo = ctx.structure.last_swing_high, ctx.structure.last_swing_low
        if hi is None or lo is None or hi <= lo:
            return None
        swing = hi - lo
        retrace = (hi - close) / swing if up else (close - lo) / swing
        lo_b = float(cfg.get("retrace_min", 0.25))
        hi_b = float(cfg.get("retrace_max", 0.75))
        if not (lo_b <= retrace <= hi_b):
            return None

        # 2 — RSI reset + turn
        look = int(cfg.get("rsi_lookback", 6))
        band = float(cfg.get("rsi_reset", 45))
        window = df["rsi"].tail(look + 1)
        now, prev = float(window.iloc[-1]), float(window.iloc[-2])
        if up and not (float(window.min()) < band and now > prev):
            return None
        if not up and not (float(window.max()) > 100 - band and now < prev):
            return None

        # 3 — candle trigger; 4 — no absorption wick against
        pattern = (candles.bullish_confirmation(df) if up
                   else candles.bearish_confirmation(df))
        if pattern is None or candles.wick_against(df, direction):
            return None

        # 5 — scorecard gate
        total, pts, notes = scorecard.score(ctx, direction)
        if total < int(cfg.get("min_score", 6)):
            return None

        reasons = [
            f"EMA50 retest {ema50:g} (masofa {abs(close - ema50) / atr:.2f}×ATR)"
            f" · retrace {retrace * 100:.0f}%",
            f"trigger: {pattern} · RSI {prev:.0f}→{now:.0f}",
            *notes,
        ]
        return StrategyMatch(name=self.name, code=self.code, direction=direction,
                             score=total, scorecard=pts, reasons=reasons)

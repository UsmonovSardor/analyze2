"""Setup B — Range Breakout with Retest (docs/strategies/strategy.md §Setup B).

Brooks breakout analysis + Nison confirmation, mirrored for breakdowns:
  1. a defined range: the pre-breakout band (range_bars) is narrow (≤ band_atr×ATR)
  2. a breakout CLOSE beyond the boundary on volume ≥ vol_mult× the 20-bar average
  3. entry = retest holding the broken level (within retest_atr×ATR, not closed
     back inside) or a strong trend bar right after the break
  4. bull/bear-trap rejection: any close back through the level after the break
     kills the setup (institutional absorption)
  5. scorecard total ≥ min_score
"""
from __future__ import annotations

from . import candles, scorecard
from .base import DetectorContext, StrategyMatch


class RangeBreakout:
    code = "B"
    name = "Range Breakout"

    def detect(self, ctx: DetectorContext) -> StrategyMatch | None:
        cfg = ctx.cfg
        df = ctx.df
        bars = int(cfg.get("range_bars", 30))
        recent = int(cfg.get("breakout_window", 5))    # bars in which the break happened
        if not {"close", "high", "low", "atr"} <= set(df.columns) \
                or len(df) < bars + recent + 5:
            return None
        atr = float(df["atr"].iloc[-1])
        if atr <= 0:
            return None

        # 1 — the pre-breakout range and its compression
        pre = df.iloc[-(bars + recent):-recent]
        range_high = float(pre["high"].max())
        range_low = float(pre["low"].min())
        if (range_high - range_low) > float(cfg.get("band_atr", 6.0)) * atr:
            return None                                # too wide to be "a range"

        window = df.iloc[-recent:]
        close = float(df["close"].iloc[-1])

        for direction, level, broke in (
                ("BUY", range_high, window["close"] > range_high),
                ("SELL", range_low, window["close"] < range_low)):
            if not bool(broke.any()):
                continue
            up = direction == "BUY"
            first = int(broke.values.argmax())          # breakout bar within window

            # 2 — breakout volume
            if "volume" in df and float(df["volume"].tail(21).mean()) > 0:
                avg20 = float(df["volume"].iloc[-21:-1].mean())
                brk_vol = float(window["volume"].iloc[first])
                if brk_vol < float(cfg.get("breakout_vol_mult", 1.5)) * avg20:
                    continue

            # 4 — trap: any close back through the level AFTER the breakout bar
            after = window["close"].iloc[first + 1:]
            trapped = bool((after < level).any()) if up else bool((after > level).any())
            if trapped:
                continue

            # 3 — retest holding the level, or immediate strong trend bar
            near = abs(close - level) <= float(cfg.get("retest_atr", 0.5)) * atr
            holding = close >= level if up else close <= level
            strong = candles.is_strong_trend_bar(df, direction)
            if not ((near and holding) or (first == recent - 1 and strong)):
                continue
            if candles.wick_against(df, direction):
                continue

            total, pts, notes = scorecard.score(ctx, direction)
            if total < int(cfg.get("min_score", 6)):
                continue

            kind = "retest" if near else "breakout bar"
            reasons = [
                f"range {range_low:g}–{range_high:g} ({bars} bar) "
                f"{'yuqoriga' if up else 'pastga'} buzildi · kirish: {kind}",
                *notes,
            ]
            return StrategyMatch(name=self.name, code=self.code, direction=direction,
                                 score=total, scorecard=pts, reasons=reasons)
        return None

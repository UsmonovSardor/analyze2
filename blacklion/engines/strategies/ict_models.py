"""ICT phase-2 detectors (docs/strategies/strategy.md §ICT Smart Money Models).

HTF-expressible ports composed from the outputs the ICT/Liquidity/OB/FVG
engines already compute — no lower-timeframe data needed. The 5m/1m-native
models (Judas timing legs, Venom, MMXM entries) stay deferred; these three
capture the catalog's core smart-money logic on M15/H1:

- Turtle Soup: time-based liquidity SWEPT, then a structure shift back — enter
  the reversal with an aligned FVG as the retest zone.
- Unicorn: breaker + FVG OVERLAP at the entry zone, with a liquidity draw (DOL)
  in the profit direction.
- AMD/PO3: manipulation (stop-hunt sweep) resolved into the distribution leg,
  structure agreeing.
"""
from __future__ import annotations

from . import candles, scorecard
from .base import DetectorContext, StrategyMatch


def _zones_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return max(a[0], b[0]) <= min(a[1], b[1])


class TurtleSoup:
    code = "TSOUP"
    name = "ICT Turtle Soup"
    emoji = "🐢"
    tagline = ("Likvidlik supurilib (stop-hunt), struktura orqaga siljigach "
               "reversalga kirish — FVG retest zonasi bilan")

    def detect(self, ctx: DetectorContext) -> StrategyMatch | None:
        liq = ctx.liquidity
        if not (liq.liquidity_swept and liq.sweep_direction):
            return None
        direction = "BUY" if liq.sweep_direction == "bullish" else "SELL"
        up = direction == "BUY"

        # structure must have SHIFTED back in the reversal direction (MSS/CISD
        # proxy: a fresh CHOCH — or BOS — printed the same way)
        st = ctx.structure
        shifted = (st.choch and st.choch_direction == liq.sweep_direction) or \
                  (st.bos and st.bos_direction == liq.sweep_direction)
        if not shifted:
            return None
        # an aligned FVG is the retest zone the model enters from
        fvg = ctx.fvg.nearest
        if fvg is None or fvg.type != ("bullish" if up else "bearish"):
            return None
        if candles.wick_against(ctx.df, direction):
            return None

        total, pts, notes = scorecard.score(ctx, direction)
        if total < int(ctx.cfg.get("min_score", 6)):
            return None
        hunt = " (stop-hunt)" if liq.stop_hunt else ""
        reasons = [
            f"{'sell-side' if up else 'buy-side'} likvidlik supurildi{hunt}"
            + (f" · pool {liq.nearest_pool:g}" if liq.nearest_pool else ""),
            f"struktura {'CHOCH' if st.choch else 'BOS'} bilan qaytdi · "
            f"FVG retest {fvg.gap_low:g}–{fvg.gap_high:g}",
            *notes,
        ]
        return StrategyMatch(name=self.name, code=self.code, direction=direction,
                             score=total, scorecard=pts, reasons=reasons)


class Unicorn:
    code = "UNICORN"
    name = "ICT Unicorn"
    emoji = "🦄"
    tagline = ("Breaker + FVG bir zonada USTMA-UST kelganda kirish — "
               "foyda yo'nalishida likvidlik (DOL) bilan")

    def detect(self, ctx: DetectorContext) -> StrategyMatch | None:
        if not ctx.ict.breaker_block:
            return None
        st = ctx.structure
        if st.trend.bullish:
            direction = "BUY"
        elif st.trend.bearish:
            direction = "SELL"
        else:
            return None
        up = direction == "BUY"

        ob = ctx.order_block.best
        fvg = ctx.fvg.nearest
        want = "bullish" if up else "bearish"
        if ob is None or fvg is None or ob.type != want or fvg.type != want:
            return None
        # the Unicorn IS the overlap — breaker (OB proxy) ∩ FVG
        if not _zones_overlap((ob.price_low, ob.price_high),
                              (fvg.gap_low, fvg.gap_high)):
            return None
        # DOL: resting liquidity in the PROFIT direction to draw price
        dol = (ctx.liquidity.buy_side_liquidity if up
               else ctx.liquidity.sell_side_liquidity)
        if not dol:
            return None
        if candles.wick_against(ctx.df, direction):
            return None

        total, pts, notes = scorecard.score(ctx, direction)
        if total < int(ctx.cfg.get("min_score", 6)):
            return None
        lo = max(ob.price_low, fvg.gap_low)
        hi = min(ob.price_high, fvg.gap_high)
        reasons = [
            f"breaker + FVG ustma-ust {lo:g}–{hi:g} (Unicorn zona)",
            f"DOL: {'buy-side' if up else 'sell-side'} likvidlik foyda yo'nalishida",
            *notes,
        ]
        return StrategyMatch(name=self.name, code=self.code, direction=direction,
                             score=total, scorecard=pts, reasons=reasons)


class AMDPowerOfThree:
    code = "AMD"
    name = "ICT AMD / PO3"
    emoji = "⚡"
    tagline = ("Accumulation → Manipulation (stop-hunt) → Distribution: "
               "manipulyatsiya yakunlanib, distribution boshlanganda kirish")

    def detect(self, ctx: DetectorContext) -> StrategyMatch | None:
        if ctx.ict.amd_phase != "Distribution":
            return None
        liq = ctx.liquidity
        # the manipulation leg must actually have taken liquidity
        if not (liq.liquidity_swept and liq.stop_hunt):
            return None
        direction = "BUY" if liq.sweep_direction == "bullish" else "SELL"
        # distribution must run WITH the printed structure
        st = ctx.structure
        aligned = (st.trend.bullish if direction == "BUY" else st.trend.bearish) \
            or (st.bos and st.bos_direction == liq.sweep_direction)
        if not aligned:
            return None
        if candles.wick_against(ctx.df, direction):
            return None

        total, pts, notes = scorecard.score(ctx, direction)
        if total < int(ctx.cfg.get("min_score", 6)):
            return None
        reasons = [
            "AMD: manipulyatsiya (stop-hunt) yakunlandi → Distribution fazasi",
            f"sweep {'pastdan' if direction == 'BUY' else 'yuqoridan'}"
            + (f" · pool {liq.nearest_pool:g}" if liq.nearest_pool else ""),
            *notes,
        ]
        return StrategyMatch(name=self.name, code=self.code, direction=direction,
                             score=total, scorecard=pts, reasons=reasons)

"""7-factor confluence scorecard (docs/strategies/strategy.md §Confluence Scorecard).

Max 10 points; the catalog's minimum to signal is 6. The crypto-specific "BTC
context" factor generalizes to `macro` = higher-timeframe agreement (forex/metals
have no BTC; a DXY/correlation feed can upgrade this later).

| factor  | pts | judged by                                                    |
| trend   | 0-2 | EMA50/EMA200 stack + price location (mirrored for shorts)    |
| level   | 0-2 | how many real zones coincide at entry (OB / FVG / OTE)       |
| volume  | 0-2 | entry-bar expansion + quiet pullback                          |
| rsi     | 0-1 | reset past the band and turning in trade direction            |
| macro   | 0-1 | higher-timeframe trend agrees                                 |
| room    | 0-1 | nearest opposing swing ≥ 2R away                              |
| candle  | 0-1 | named trigger pattern on the signal bar                       |
"""
from __future__ import annotations

from . import candles
from .base import DetectorContext


def score(ctx: DetectorContext, direction: str) -> tuple[int, dict[str, int], list[str]]:
    """(total, per-factor points, valued notes) for the candidate direction."""
    df = ctx.df
    up = direction == "BUY"
    pts: dict[str, int] = {}
    notes: list[str] = []

    # ── trend (0-2) ────────────────────────────────────────────────────────
    close = float(df["close"].iloc[-1])
    ema50 = float(df["ema50"].iloc[-1]) if "ema50" in df else close
    ema200 = float(df["ema200"].iloc[-1]) if "ema200" in df else close
    stacked = ema50 > ema200 if up else ema50 < ema200
    beyond200 = close > ema200 if up else close < ema200
    pts["trend"] = 2 if (stacked and beyond200) else 1 if beyond200 else 0
    if pts["trend"]:
        notes.append(f"trend: EMA50 {ema50:g} {'>' if up else '<'} EMA200 {ema200:g}"
                     f" ({pts['trend']}/2)")

    # ── level (0-2): coinciding real zones at entry ───────────────────────
    ob = ctx.order_block.best
    ob_ok = ob is not None and ob.type == ("bullish" if up else "bearish")
    fvg = ctx.fvg.nearest
    fvg_ok = fvg is not None and fvg.type == ("bullish" if up else "bearish")
    zones = int(ob_ok) + int(fvg_ok) + int(ctx.ict.ote)
    pts["level"] = 2 if zones >= 2 else 1 if zones == 1 else 0
    if zones:
        what = [w for w, ok in (("OB", ob_ok), ("FVG", fvg_ok), ("OTE", ctx.ict.ote)) if ok]
        notes.append(f"level: {'+'.join(what)} mos ({pts['level']}/2)")

    # ── volume (0-2): expansion at entry, quiet pullback ──────────────────
    pts["volume"] = 1                                  # neutral when unavailable
    if "volume" in df and len(df) >= 21 and float(df["volume"].tail(21).mean()) > 0:
        avg20 = float(df["volume"].iloc[-21:-1].mean())
        now = float(df["volume"].iloc[-1])
        quiet_pullback = float(df["volume"].iloc[-4:-1].mean()) < avg20
        expanding = now >= 1.2 * avg20
        pts["volume"] = 2 if (expanding and quiet_pullback) else \
            1 if (expanding or quiet_pullback) else 0
        notes.append(f"volume: {now / avg20:.1f}× o'rtacha ({pts['volume']}/2)")

    # ── rsi (0-1): reset + turn ────────────────────────────────────────────
    pts["rsi"] = 0
    if "rsi" in df and len(df) >= 7:
        window = df["rsi"].tail(7)
        now, prev = float(window.iloc[-1]), float(window.iloc[-2])
        if up and float(window.min()) < 45 and now > prev:
            pts["rsi"] = 1
            notes.append(f"RSI reset {float(window.min()):.0f}→{now:.0f} (1/1)")
        elif not up and float(window.max()) > 55 and now < prev:
            pts["rsi"] = 1
            notes.append(f"RSI rolldown {float(window.max()):.0f}→{now:.0f} (1/1)")

    # ── macro (0-1): higher-timeframe agreement ───────────────────────────
    pts["macro"] = int(ctx.htf_bullish is not None and ctx.htf_bullish == up)
    if pts["macro"]:
        notes.append("HTF trend mos (1/1)")

    # ── room (0-1): opposing swing ≥ ~2R away (R ≈ 1.2×ATR proxy) ─────────
    pts["room"] = 0
    atr = float(df["atr"].iloc[-1]) if "atr" in df else 0.0
    opposing = (ctx.structure.last_swing_high if up
                else ctx.structure.last_swing_low)
    if atr > 0 and opposing is not None:
        dist = (opposing - close) if up else (close - opposing)
        if dist >= 2 * 1.2 * atr:
            pts["room"] = 1
            notes.append(f"room: qarshilik {dist / atr:.1f}×ATR uzoq (1/1)")

    # ── candle (0-1): trigger pattern ─────────────────────────────────────
    pattern = (candles.bullish_confirmation(df) if up
               else candles.bearish_confirmation(df))
    pts["candle"] = int(pattern is not None)
    if pattern:
        notes.append(f"sham: {pattern} (1/1)")

    return sum(pts.values()), pts, notes

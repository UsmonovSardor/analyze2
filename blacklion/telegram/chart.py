"""Signal / outcome chart — a dark, professional candlestick snapshot of the setup
with the trade's entry / stop / TP levels drawn on, rendered to PNG bytes for
Telegram.

matplotlib is imported lazily with the Agg backend, so importing this module
never needs a display, and any render failure degrades to text (returns None)
rather than dropping the signal. Candles are the real MT5 OHLC bars. The feed
frame drops absolute timestamps, so the x-axis is reconstructed as clock-aligned
bar times ending at the render moment (matching how MT5 aligns its bars) — real
enough to read like the terminal, honest that it is approximate on gaps.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from io import BytesIO

from ..core import config
from ..core.logging import get_logger

log = get_logger("telegram.chart")

# palette — a calm trading-terminal dark theme, MT5-style candle colours
_BG = "#0e1116"
_PANEL = "#131722"
_GRID = "#1f2733"
_TEXT = "#c9d1d9"
_MUTED = "#6b7686"
_UP = "#26a69a"
_DOWN = "#ef5350"
_ENTRY = "#e8eaed"
_STOP = "#ff5c6c"
_TP = "#3fb68b"

_TF_MIN = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


def _dec(price: float) -> int:
    ap = abs(price)
    return 2 if ap >= 100 else (3 if ap >= 10 else 5)


def _bar_times(n: int, timeframe: str, end_epoch: float) -> list[datetime]:
    """Clock-aligned bar open-times ending at (and including) the current bar."""
    off = float(config.env("BL_TZ_OFFSET_HOURS", "5"))
    tz = timezone(timedelta(hours=off))
    step = _TF_MIN.get(timeframe, 60)
    end = datetime.fromtimestamp(int(end_epoch), tz=tz)
    end -= timedelta(minutes=end.minute % step, seconds=end.second,
                     microseconds=end.microsecond)
    return [end - timedelta(minutes=step * (n - 1 - i)) for i in range(n)]


def render_signal_chart(sig, df, timeframe: str = "H1", bars: int = 60,
                        outcome: tuple[str, float | None] | None = None,
                        end_epoch: float | None = None) -> bytes | None:
    """PNG snapshot of the last `bars` candles with trade levels. `outcome`, when
    given as (status, result_r), stamps the result on the chart. Returns None if
    matplotlib is unavailable or anything goes wrong (caller falls back to text)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:                                   # pragma: no cover
        log.warning("ChartLibMissing", error=str(exc))
        return None
    try:
        return _draw(plt, sig, df, timeframe, bars, outcome,
                     end_epoch if end_epoch is not None else time.time())
    except Exception as exc:
        log.warning("ChartRenderError", symbol=getattr(sig, "symbol", "?"),
                    error=str(exc))
        return None


_OUTCOME_BADGE = {
    "tp1": ("TP1 ✓", _UP), "tp2": ("TP2 ✓", _UP), "tp3": ("TP3 ✓✓✓", _UP),
    "stopped": ("STOP", _DOWN), "breakeven": ("BREAKEVEN", _MUTED),
    "expired": ("BEKOR", _MUTED),
}


def _draw(plt, sig, df, timeframe, bars, outcome, end_epoch) -> bytes:
    d = df.tail(bars).reset_index(drop=True)
    o, h, lows, c = (d["open"].to_numpy(), d["high"].to_numpy(),
                     d["low"].to_numpy(), d["close"].to_numpy())
    n = len(d)
    dec = _dec(sig.entry)
    times = _bar_times(n, timeframe, end_epoch)
    levels = [
        (sig.tp3, _TP, f"TP3 {sig.tp3:.{dec}f}"),
        (sig.tp2, _TP, f"TP2 {sig.tp2:.{dec}f}"),
        (sig.tp1, _TP, f"TP1 {sig.tp1:.{dec}f}"),
        (sig.entry, _ENTRY, f"Kirish {sig.entry:.{dec}f}"),
        (sig.stop_loss, _STOP, f"Stop {sig.stop_loss:.{dec}f}"),
    ]

    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=130)
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_PANEL)

    # risk (entry↔stop) and reward (entry↔tp3) shading
    ax.axhspan(min(sig.entry, sig.stop_loss), max(sig.entry, sig.stop_loss),
               color=_DOWN, alpha=0.08, zorder=0)
    ax.axhspan(min(sig.entry, sig.tp3), max(sig.entry, sig.tp3),
               color=_UP, alpha=0.07, zorder=0)

    # candles
    w = 0.62
    span = max(h.max() - lows.min(), 1e-9)
    for i in range(n):
        up = c[i] >= o[i]
        col = _UP if up else _DOWN
        ax.plot([i, i], [lows[i], h[i]], color=col, linewidth=0.9, zorder=2)
        lo_body, hi_body = (o[i], c[i]) if up else (c[i], o[i])
        ax.add_patch(plt.Rectangle((i - w / 2, lo_body), w,
                                   max(hi_body - lo_body, span * 1e-3),
                                   facecolor=col, edgecolor=col, zorder=3))

    # trade levels + TradingView-style price tags pinned to the right edge
    for price, color, text in levels:
        ax.axhline(price, color=color, linewidth=1.2,
                   linestyle="--" if color == _ENTRY else "-", alpha=0.9, zorder=4)
        ax.text(n + 0.4, price, text, va="center", ha="left", color=_BG,
                fontsize=8, fontweight="bold", zorder=6,
                bbox=dict(boxstyle="round,pad=0.28", facecolor=color, edgecolor="none"))

    arrow = "▲ BUY" if sig.direction == "BUY" else "▼ SELL"
    acol = _UP if sig.direction == "BUY" else _DOWN
    ax.set_title(f"{sig.symbol}   ·   {timeframe}", color=_TEXT,
                 fontsize=13, fontweight="bold", loc="left", pad=12)
    ax.text(0.995, 1.02, arrow, transform=ax.transAxes, ha="right", va="bottom",
            color=acol, fontsize=12, fontweight="bold")
    ax.text(0.5, 0.5, "BLACK LION AI", transform=ax.transAxes, ha="center",
            va="center", color=_TEXT, fontsize=22, fontweight="bold", alpha=0.05,
            zorder=1)

    if outcome is not None:
        status, result_r = outcome
        text, col = _OUTCOME_BADGE.get(status, (status.upper(), _MUTED))
        if result_r is not None:
            text += f"   {result_r:+.2f}R"
        ax.text(0.012, 0.965, text, transform=ax.transAxes, ha="left", va="top",
                color=_BG, fontsize=11, fontweight="bold", zorder=7,
                bbox=dict(boxstyle="round,pad=0.4", facecolor=col, edgecolor="none"))

    # time axis — a handful of clock-aligned labels, MT5-style
    ax.margins(x=0.02)
    ax.set_xlim(-1, n + 9)
    step = max(1, n // 6)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([times[i].strftime("%d %b %H:%M") for i in ticks],
                       rotation=0, fontsize=7.5)
    ax.yaxis.tick_right()
    ax.tick_params(colors=_MUTED, labelsize=8)
    for s in ax.spines.values():
        s.set_color(_GRID)
    ax.grid(True, color=_GRID, linewidth=0.5, alpha=0.6)

    buf = BytesIO()
    fig.savefig(buf, format="png", facecolor=_BG, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()

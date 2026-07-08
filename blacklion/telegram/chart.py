"""Signal chart — a dark, professional candlestick snapshot of the setup with the
trade's entry / stop / TP levels drawn on, rendered to PNG bytes for Telegram.

matplotlib is imported lazily with the Agg backend, so importing this module
never needs a display, and any render failure degrades to text (returns None)
rather than dropping the signal. Candles are the real MT5 OHLC bars; the x-axis
carries no absolute timestamps (the finalized feed frame drops them), so we plot
by bar order and put the timeframe in the title — honest, not fake-precise.
"""
from __future__ import annotations

from io import BytesIO

from ..core.logging import get_logger

log = get_logger("telegram.chart")

# palette — a calm trading-terminal dark theme
_BG = "#0e1116"
_PANEL = "#131722"
_GRID = "#1f2733"
_TEXT = "#c9d1d9"
_UP = "#26a269"
_DOWN = "#e01b24"
_ENTRY = "#e8eaed"
_STOP = "#ff5c6c"
_TP = "#3fb68b"


def _dec(price: float) -> int:
    ap = abs(price)
    return 2 if ap >= 100 else (3 if ap >= 10 else 5)


def render_signal_chart(sig, df, timeframe: str = "H1", bars: int = 60) -> bytes | None:
    """Return a PNG snapshot of the last `bars` candles with the trade levels, or
    None if matplotlib is unavailable or anything goes wrong."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:                                   # pragma: no cover
        log.warning("ChartLibMissing", error=str(exc))
        return None
    try:
        return _draw(plt, sig, df, timeframe, bars)
    except Exception as exc:
        log.warning("ChartRenderError", symbol=getattr(sig, "symbol", "?"),
                    error=str(exc))
        return None


def _draw(plt, sig, df, timeframe: str, bars: int) -> bytes:
    d = df.tail(bars).reset_index(drop=True)
    o, h, lows, c = (d["open"].to_numpy(), d["high"].to_numpy(),
                     d["low"].to_numpy(), d["close"].to_numpy())
    n = len(d)
    dec = _dec(sig.entry)
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
    for i in range(n):
        up = c[i] >= o[i]
        col = _UP if up else _DOWN
        ax.plot([i, i], [lows[i], h[i]], color=col, linewidth=0.9, zorder=2)
        lo_body, hi_body = (o[i], c[i]) if up else (c[i], o[i])
        ax.add_patch(plt.Rectangle((i - w / 2, lo_body), w,
                                   max(hi_body - lo_body, (h.max() - lows.min()) * 1e-3),
                                   facecolor=col, edgecolor=col, zorder=3))

    # trade levels + TradingView-style price tags pinned to the right edge
    for price, color, text in levels:
        ax.axhline(price, color=color, linewidth=1.2,
                   linestyle="--" if color == _ENTRY else "-", alpha=0.9, zorder=4)
        ax.text(n + 0.4, price, text, va="center", ha="left", color=_BG,
                fontsize=8, fontweight="bold", zorder=6,
                bbox=dict(boxstyle="round,pad=0.28", facecolor=color,
                          edgecolor="none"))

    arrow = "▲ BUY" if sig.direction == "BUY" else "▼ SELL"
    acol = _UP if sig.direction == "BUY" else _DOWN
    ax.set_title(f"{sig.symbol}   ·   {timeframe}", color=_TEXT,
                 fontsize=13, fontweight="bold", loc="left", pad=12)
    ax.text(0.995, 1.02, arrow, transform=ax.transAxes, ha="right", va="bottom",
            color=acol, fontsize=12, fontweight="bold")
    ax.text(0.5, 0.5, "BLACK LION AI", transform=ax.transAxes, ha="center",
            va="center", color=_TEXT, fontsize=22, fontweight="bold", alpha=0.05,
            zorder=1)

    # cosmetics: price axis on the right, no x ticks (bar order, not clock time)
    ax.margins(x=0.02)
    ax.set_xlim(-1, n + 9)
    ax.set_xticks([])
    ax.yaxis.tick_right()
    ax.tick_params(colors=_TEXT, labelsize=8)
    for s in ax.spines.values():
        s.set_color(_GRID)
    ax.grid(True, color=_GRID, linewidth=0.5, alpha=0.6)

    buf = BytesIO()
    fig.savefig(buf, format="png", facecolor=_BG, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()

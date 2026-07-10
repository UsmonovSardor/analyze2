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

# palette — TradingView/MT5 dark terminal. Muted, professional, not "infographic".
_BG = "#131722"
_PANEL = "#131722"
_GRID = "#232733"
_AXIS = "#363a45"
_TEXT = "#d1d4dc"
_MUTED = "#787b86"
_UP = "#26a69a"
_DOWN = "#ef5350"
_ENTRY = "#b2b5be"
_STOP = "#ef5350"
_TP = "#26a69a"

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
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter

    d = df.tail(bars).reset_index(drop=True)
    o, h, lows, c = (d["open"].to_numpy(), d["high"].to_numpy(),
                     d["low"].to_numpy(), d["close"].to_numpy())
    n = len(d)
    dec = _dec(sig.entry)
    times = _bar_times(n, timeframe, end_epoch)
    last = float(c[-1])
    levels = [                                  # (price, colour, short tag)
        (sig.tp3, _TP, "TP3"), (sig.tp2, _TP, "TP2"), (sig.tp1, _TP, "TP1"),
        (sig.entry, _ENTRY, "E"), (sig.stop_loss, _STOP, "SL"),
    ]

    # y-range covers candles AND every level, with a little headroom so tags fit
    prices = [h.max(), lows.min(), sig.tp3, sig.stop_loss, sig.entry]
    ymax, ymin = max(prices), min(prices)
    pad = max((ymax - ymin) * 0.06, 1e-9)
    ymax, ymin = ymax + pad, ymin - pad

    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=140)
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_PANEL)

    # candles — thin wicks + slim bodies, terminal proportions
    w = 0.6
    span = max(ymax - ymin, 1e-9)
    for i in range(n):
        up = c[i] >= o[i]
        col = _UP if up else _DOWN
        ax.plot([i, i], [lows[i], h[i]], color=col, linewidth=0.8,
                solid_capstyle="round", zorder=3)
        lo_body, hi_body = (o[i], c[i]) if up else (c[i], o[i])
        ax.add_patch(Rectangle((i - w / 2, lo_body), w,
                               max(hi_body - lo_body, span * 6e-4),
                               facecolor=col, edgecolor=col, linewidth=0.4, zorder=4))

    # trade levels — thin lines spanning the candles, small flat tag in the gutter
    for price, color, tag in levels:
        dashed = tag == "E"
        ax.plot([-0.5, n - 0.5], [price, price], color=color, linewidth=1.0,
                linestyle=(0, (5, 3)) if dashed else "-", alpha=0.85, zorder=5)
        txtcol = _BG if not dashed else _TEXT
        facecol = color if not dashed else _PANEL
        ax.text(n + 0.6, price, f"{tag} {price:.{dec}f}", va="center", ha="left",
                color=txtcol, fontsize=8, fontweight="bold", zorder=7,
                bbox=dict(boxstyle="square,pad=0.32", facecolor=facecol,
                          edgecolor=color, linewidth=0.8))

    # current price — MT5-style dashed marker + axis tag, but skip it when it
    # nearly coincides with a level tag (a fresh signal fires AT the current close,
    # so entry ≈ last → the two tags would overlap into an unreadable smear).
    near = min(abs(last - p) for p, _c, _t in levels)
    if near > span * 0.022:
        ax.plot([-0.5, n - 0.5], [last, last], color=_MUTED, linewidth=0.8,
                linestyle=(0, (2, 3)), alpha=0.7, zorder=5)
        ax.text(n + 0.6, last, f"{last:.{dec}f}", va="center", ha="left", color=_BG,
                fontsize=7.5, fontweight="bold", zorder=8,
                bbox=dict(boxstyle="square,pad=0.3", facecolor=_MUTED, edgecolor="none"))

    # header: symbol · TF (left), direction (right)
    arrow = "▲ BUY" if sig.direction == "BUY" else "▼ SELL"
    acol = _UP if sig.direction == "BUY" else _DOWN
    ax.text(0.0, 1.045, f"{sig.symbol}", transform=ax.transAxes, ha="left",
            va="bottom", color=_TEXT, fontsize=14, fontweight="bold")
    ax.text(0.128, 1.052, f"· {timeframe}", transform=ax.transAxes, ha="left",
            va="bottom", color=_MUTED, fontsize=10.5, fontweight="bold")
    ax.text(1.0, 1.05, arrow, transform=ax.transAxes, ha="right", va="bottom",
            color=acol, fontsize=12, fontweight="bold")

    # faint corner watermark (not a big centre stamp)
    ax.text(0.5, 0.5, "BLACK LION AI", transform=ax.transAxes, ha="center",
            va="center", color=_TEXT, fontsize=20, fontweight="bold", alpha=0.035,
            zorder=1)

    if outcome is not None:
        status, result_r = outcome
        text, col = _OUTCOME_BADGE.get(status, (status.upper(), _MUTED))
        if result_r is not None:
            text += f"  {result_r:+.2f}R"
        ax.text(0.014, 0.96, text, transform=ax.transAxes, ha="left", va="top",
                color=_BG, fontsize=10.5, fontweight="bold", zorder=9,
                bbox=dict(boxstyle="square,pad=0.4", facecolor=col, edgecolor="none"))

    # axes — subtle horizontal grid, clean right price scale, sparse time labels
    ax.set_xlim(-1, n + 8)
    ax.set_ylim(ymin, ymax)
    step = max(1, n // 7)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([times[i].strftime("%d %b\n%H:%M") for i in ticks],
                       rotation=0, fontsize=7.5)
    ax.yaxis.tick_right()
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.{dec}f}"))
    ax.tick_params(colors=_MUTED, labelsize=8, length=0)
    ax.grid(True, axis="y", color=_GRID, linewidth=0.6, alpha=0.7)
    ax.grid(True, axis="x", color=_GRID, linewidth=0.5, alpha=0.35)
    ax.set_axisbelow(True)
    for side, sp in ax.spines.items():
        sp.set_visible(side in ("bottom", "right"))
        sp.set_color(_AXIS)
        sp.set_linewidth(0.8)

    buf = BytesIO()
    fig.savefig(buf, format="png", facecolor=_BG, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()

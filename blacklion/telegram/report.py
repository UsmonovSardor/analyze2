"""Weekly performance report — equity curve PNG + per-strategy table.

Everything is derived from the journal's closed trades (R units, not money —
demo balances lie, R doesn't). Rendering degrades to text like chart.py: any
matplotlib failure returns None and the caption still ships.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from ..ai.stats import bucket_stats
from ..core.logging import get_logger
from .client import esc

log = get_logger("telegram.report")

_BG, _PANEL, _GRID, _AXIS = "#131722", "#131722", "#232733", "#363a45"
_TEXT, _MUTED, _UP, _DOWN = "#d1d4dc", "#787b86", "#26a69a", "#ef5350"


def render_equity_chart(rows: list[dict]) -> bytes | None:
    """Cumulative-R equity curve with drawdown shading. rows must carry
    result_r + closed_at (Journal.closed_rows)."""
    rows = sorted((r for r in rows if r.get("closed_at")),
                  key=lambda r: r["closed_at"])
    if len(rows) < 2:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception as exc:                               # pragma: no cover
        log.warning("ReportLibMissing", error=str(exc))
        return None
    try:
        eq = np.cumsum([float(r["result_r"]) for r in rows])
        peak = np.maximum.accumulate(eq)
        times = [datetime.fromtimestamp(r["closed_at"], tz=timezone.utc)
                 for r in rows]

        fig, ax = plt.subplots(figsize=(10, 4.6), dpi=140)
        fig.patch.set_facecolor(_BG)
        ax.set_facecolor(_PANEL)
        ax.plot(times, eq, color=_UP if eq[-1] >= 0 else _DOWN, linewidth=1.6)
        ax.fill_between(times, eq, peak, color=_DOWN, alpha=0.15,
                        label="drawdown")
        ax.axhline(0, color=_MUTED, linewidth=0.8, linestyle=(0, (4, 3)))
        dd = float((peak - eq).max())
        ax.set_title(f"Equity (R) — jami {eq[-1]:+.1f}R · max drawdown {dd:.1f}R",
                     color=_TEXT, fontsize=11, fontweight="bold", loc="left")
        ax.text(0.5, 0.5, "BLACK LION AI", transform=ax.transAxes, ha="center",
                va="center", color=_TEXT, fontsize=18, fontweight="bold",
                alpha=0.035)
        ax.tick_params(colors=_MUTED, labelsize=8, length=0)
        ax.grid(True, color=_GRID, linewidth=0.6, alpha=0.7)
        ax.set_axisbelow(True)
        for side, sp in ax.spines.items():
            sp.set_visible(side in ("bottom", "left"))
            sp.set_color(_AXIS)
        buf = BytesIO()
        fig.savefig(buf, format="png", facecolor=_BG, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except Exception as exc:
        log.warning("ReportRenderError", error=str(exc))
        return None


def weekly_report_caption(rows: list[dict], days: int = 7) -> str:
    """Uzbek weekly summary: totals + per-strategy table + honest note."""
    if not rows:
        return ("📈 <b>Haftalik hisobot</b>\n"
                "Bu davrda yopilgan savdolar yo'q.")
    total_r = sum(float(r["result_r"]) for r in rows)
    wins = sum(1 for r in rows if float(r["result_r"]) > 0)
    losses = [r for r in rows if float(r["result_r"]) < 0]
    full_stops = sum(1 for r in losses if r["status"] == "stopped")
    lines = [
        f"📈 <b>Haftalik hisobot</b> (oxirgi {days} kun)",
        f"Σ <b>{total_r:+.2f}R</b> · {len(rows)} savdo · "
        f"win {wins / len(rows) * 100:.0f}%",
    ]
    if losses:
        avg_loss = sum(float(r["result_r"]) for r in losses) / len(losses)
        lines.append(f"O'rtacha zarar {avg_loss:.2f}R · "
                     f"to'liq stop {full_stops}/{len(losses)}")
    lines.append("")
    lines.append("<b>Strategiyalar:</b>")
    for name, s in sorted(bucket_stats(rows).items(), key=lambda kv: -kv[1]["n"]):
        lines.append(f"  • {esc(name)}: n={s['n']} · win {s['win_rate'] * 100:.0f}% "
                     f"· {s['avg_r']:+.2f}R")
    best = max(rows, key=lambda r: float(r["result_r"]))
    worst = min(rows, key=lambda r: float(r["result_r"]))
    lines += ["",
              f"🏆 Eng yaxshi: {esc(best['symbol'])} {float(best['result_r']):+.2f}R"
              f" · 📉 Eng yomon: {esc(worst['symbol'])} {float(worst['result_r']):+.2f}R",
              "⚠️ <i>Demo forward-test · R birliklarida (pul emas)</i>"]
    return "\n".join(lines)

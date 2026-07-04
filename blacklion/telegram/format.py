"""Telegram message formatting (Uzbek) — SRS doc 23 §10 templates.

Pure functions: given a Signal / outcome / stats dict, return an HTML string.
No I/O, so every template is unit-tested without a network.
"""
from __future__ import annotations

from ..engines.rule_engine import Signal
from ..journal import TradeRow
from .client import esc


def _bar(score: int) -> str:
    score = max(0, min(10, round(score / 10)))
    return "▰" * score + "▱" * (10 - score)


def signal_message(sig: Signal, sig_id: int, market_ctx: str = "") -> str:
    arrow = "🟢" if sig.direction == "BUY" else "🔻"
    r = abs(sig.entry - sig.stop_loss) or 1e-9

    def gain(tp: float) -> float:
        return abs(tp - sig.entry) / sig.entry * 100

    def rr(tp: float) -> float:
        return abs(tp - sig.entry) / r

    loss_pct = abs(sig.stop_loss - sig.entry) / sig.entry * 100
    lines = [
        f"{arrow} <b>{sig.direction}</b> · <b>{esc(sig.symbol)}</b> · #{sig_id}",
        f"📊 Ishonch <b>{sig.confidence}/100</b> · konfluens {sig.confluence_score} "
        f"{_bar(sig.confidence)}",
        "",
        f"📍 Kirish: <b>{sig.entry}</b>",
        f"🛑 Stop: <b>{sig.stop_loss}</b>  <i>(−{loss_pct:.2f}%)</i>",
        f"🎯 TP1: <b>{sig.tp1}</b>  <i>(+{gain(sig.tp1):.2f}% · {rr(sig.tp1):.1f}R)</i>",
        f"🎯 TP2: <b>{sig.tp2}</b>  <i>(+{gain(sig.tp2):.2f}% · {rr(sig.tp2):.1f}R)</i>",
        f"🎯 TP3: <b>{sig.tp3}</b>  <i>(+{gain(sig.tp3):.2f}% · {rr(sig.tp3):.1f}R)</i>",
        "",
        "✅ <b>Sabablar:</b>",
    ]
    lines += [f"  • {esc(reason)}" for reason in sig.reasons]
    if market_ctx:
        lines.append(f"<i>{esc(market_ctx)}</i>")
    lines.append("⚠️ <i>Moliyaviy maslahat emas · risk 1%</i>")
    return "\n".join(lines)


_OUTCOME_LABEL = {
    "tp1": "🎯 <b>TP1 urildi</b> — 40% olindi, stop breakeven'ga",
    "tp2": "🎯 <b>TP2 urildi</b> — yana 40% olindi",
    "tp3": "✅ <b>TP3 urildi</b> — pozitsiya to'liq yopildi",
    "stopped": "🛑 <b>Stop-loss urildi</b>",
    "breakeven": "⚪ <b>Breakeven'da yopildi</b> — zarar yo'q",
}


def outcome_message(row: TradeRow, status: str, result_r: float | None = None) -> str:
    label = _OUTCOME_LABEL.get(status, f"<b>{esc(status)}</b>")
    txt = f"{label}\n#{row.id} <b>{esc(row.symbol)}</b> · {row.direction}"
    if result_r is not None:
        emo = "🟢" if result_r > 0 else ("⚪" if abs(result_r) < 0.05 else "🔴")
        txt += f"\n{emo} Natija: <b>{result_r:+.2f}R</b>"
    return txt


def daily_digest(stats: dict, signals_today: int) -> str:
    return (
        "📬 <b>Kunlik hisobot</b>\n"
        f"🎯 Bugungi signallar: <b>{signals_today}</b>\n"
        f"📂 Ochiq: {stats['open']}\n"
        f"📈 So'nggi 7 kun: {stats['wins']}/{stats['closed']} yutuq "
        f"({stats['win_rate']}%) · <b>{stats['total_r']:+.2f}R</b>")


def weekly_stats(stats: dict) -> str:
    return (
        "📊 <b>HAFTALIK HISOBOT</b>\n\n"
        f"Yopilgan: <b>{stats['closed']}</b> · Yutuq: <b>{stats['wins']}</b> "
        f"({stats['win_rate']}%)\n"
        f"Jami natija: <b>{stats['total_r']:+.2f}R</b> · Ochiq: {stats['open']}")

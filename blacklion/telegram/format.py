"""Telegram message formatting (Uzbek) — SRS doc 23 §10 templates.

Pure functions: given a Signal / outcome / stats dict, return an HTML string.
No I/O, so every template is unit-tested without a network.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from ..core import config
from ..engines.rule_engine import Signal
from ..journal import TradeRow
from .client import esc


def _local(epoch: int | None) -> datetime | None:
    """Epoch → tz-aware datetime in the display timezone (default UTC+5 Tashkent,
    matching the user's Telegram clock). Override with BL_TZ_OFFSET_HOURS."""
    if not epoch:
        return None
    off = float(config.env("BL_TZ_OFFSET_HOURS", "5"))
    return datetime.fromtimestamp(int(epoch), tz=timezone(timedelta(hours=off)))


def _dur(seconds: float) -> str:
    """Compact Uzbek duration: kun / soat / daqiqa."""
    mins = int(seconds) // 60
    hrs, mins = divmod(mins, 60)
    days, hrs = divmod(hrs, 24)
    if days:
        return f"{days}k {hrs}s"
    if hrs:
        return f"{hrs}s {mins}d"
    return f"{mins}d"


def _bar(score: int) -> str:
    score = max(0, min(10, round(score / 10)))
    return "▰" * score + "▱" * (10 - score)


# TITAN Bible 14.9 — confidence tiers by name
def confidence_tier(conf: int) -> str:
    if conf >= 95:
        return "ELITE"
    if conf >= 85:
        return "PRO"
    if conf >= 70:
        return "GOOD"
    if conf >= 50:
        return "WATCH"
    return "NO TRADE"


# 7-factor scorecard display names (order fixed for a stable caption line)
_SCORECARD_UZ = [("trend", "Trend", 2), ("level", "Zona", 2), ("volume", "Hajm", 2),
                 ("rsi", "RSI", 1), ("macro", "HTF", 1), ("room", "Joy", 1),
                 ("candle", "Sham", 1)]


def _scorecard_line(card: dict) -> str:
    parts = [f"{name} {card.get(key, 0)}/{mx}" for key, name, mx in _SCORECARD_UZ]
    total = sum(card.get(k, 0) for k, _, _ in _SCORECARD_UZ)
    return f"🎯 {' · '.join(parts)} — <b>{total}/10</b>"


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
        f"📌 <b>{esc(sig.strategy_name)}</b>",
        f"📊 Ishonch <b>{sig.confidence}/100</b> · <b>{confidence_tier(sig.confidence)}</b> "
        f"· konfluens {sig.confluence_score} {_bar(sig.confidence)}",
        *([_scorecard_line(sig.scorecard)] if sig.scorecard else []),
        "",
        f"📍 Kirish: <b>{sig.entry}</b>",
        f"🛑 Stop: <b>{sig.stop_loss}</b>  <i>(−{loss_pct:.2f}%)</i>",
        f"🎯 TP1: <b>{sig.tp1}</b>  <i>(+{gain(sig.tp1):.2f}% · {rr(sig.tp1):.1f}R)</i>",
        f"🎯 TP2: <b>{sig.tp2}</b>  <i>(+{gain(sig.tp2):.2f}% · {rr(sig.tp2):.1f}R)</i>",
        f"🎯 TP3: <b>{sig.tp3}</b>  <i>(+{gain(sig.tp3):.2f}% · {rr(sig.tp3):.1f}R)</i>",
        "",
        "🔎 <b>Tahlil:</b>",
    ]
    lines += [f"  • {esc(reason)}" for reason in sig.reasons]
    if market_ctx:
        lines.append(f"<i>{esc(market_ctx)}</i>")
    lines.append("⚠️ <i>Moliyaviy maslahat emas · risk 1%</i>")
    return "\n".join(lines)


_OUTCOME_LABEL = {
    "tp1": "🎯 <b>TP1 urildi</b> — 40% olindi, stop breakeven'ga",
    "tp2": "🎯 <b>TP2 urildi</b> — yana 40% olindi, runner trailing'da",
    "tp3": "✅ <b>TP3 urildi</b> — pozitsiya to'liq yopildi",
    "stopped": "🛑 <b>Stop-loss urildi</b>",
    "breakeven": "⚪ <b>Breakeven'da yopildi</b> — zarar yo'q",
    "trailed": "🟢 <b>Trailing stop urildi</b> — runner foyda bilan yopildi",
    "invalidated": "⚠️ <b>Struktura buzildi</b> — stop kutmasdan erta yopildi",
    "stale": "⏳ <b>Vaqt-stop</b> — harakat bo'lmadi, erta yopildi",
}


# terminal = trade fully closed; tp1/tp2 are partial scale-outs, runner still live
_TERMINAL = {"tp3", "stopped", "breakeven", "expired",
             "trailed", "invalidated", "stale"}


def outcome_message(row: TradeRow, status: str, result_r: float | None = None) -> str:
    label = _OUTCOME_LABEL.get(status, f"<b>{esc(status)}</b>")
    tf = f" · {esc(row.timeframe)}" if getattr(row, "timeframe", None) else ""
    lines = [label, f"#{row.id} <b>{esc(row.symbol)}</b> · {row.direction}{tf}"]
    strat = getattr(row, "strategy_name", "")
    if strat:
        lines.append(f"📌 {esc(strat)}")
    lines.append(f"📍 Kirish {row.entry} · 🛑 Stop {row.stop_loss}"
                 + (" · 🎫 real order" if getattr(row, "ticket", None) else ""))
    if result_r is not None:
        emo = "🟢" if result_r > 0 else ("⚪" if abs(result_r) < 0.05 else "🔴")
        tag = "Yakuniy natija" if status in _TERMINAL else "Bookqilingan"
        lines.append(f"{emo} {tag}: <b>{result_r:+.2f}R</b>")
    opened = _local(getattr(row, "created_at", None))
    if opened is not None:
        held = _dur(time.time() - row.created_at)
        if status in _TERMINAL:
            closed = _local(int(time.time()))
            lines.append(f"🕒 {opened:%d.%m.%Y %H:%M} → {closed:%H:%M} · ⏱ {held}")
        else:
            lines.append(f"🕒 Ochilgan: {opened:%d.%m %H:%M} · ⏱ {held} · runner davom etmoqda")
    return "\n".join(lines)


def daily_digest(stats: dict, signals_today: int) -> str:
    return (
        "📬 <b>Kunlik hisobot</b>\n"
        f"🎯 Bugungi signallar: <b>{signals_today}</b>\n"
        f"📂 Ochiq: {stats['open']}\n"
        f"📈 So'nggi 7 kun: {stats['wins']}/{stats['closed']} yutuq "
        f"({stats['win_rate']}%) · <b>{stats['total_r']:+.2f}R</b>")


_STATUS_EMOJI = {"HEALTHY": "🟢", "DEGRADED": "🟠", "FAILED": "🔴"}


def health_message(r) -> str:
    emo = _STATUS_EMOJI.get(r.status, "⚪")
    up_h = r.uptime_seconds // 3600
    up_m = (r.uptime_seconds % 3600) // 60
    lines = [
        f"{emo} <b>Holat: {r.status}</b>",
        f"⏱ Ishlash vaqti: {up_h}s {up_m}d",
        f"🔁 Oxirgi skan: {r.seconds_since_scan}s oldin"
        if r.seconds_since_scan is not None else "🔁 Hali skan bo'lmadi",
        f"📡 Ma'lumot oqimi: {'✅' if r.feed_ok else '❌'}",
        f"🎯 Bugungi signallar: {r.signals_today} · Ochiq: {r.open_trades}",
    ]
    if r.consecutive_errors:
        lines.append(f"⚠️ Ketma-ket xatolar: {r.consecutive_errors}")
    res = []
    if r.cpu_pct is not None:
        res.append(f"CPU {r.cpu_pct:.0f}%")
    if r.mem_pct is not None:
        res.append(f"RAM {r.mem_pct:.0f}%")
    if r.disk_pct is not None:
        res.append(f"Disk {r.disk_pct:.0f}%")
    if res:
        lines.append("🖥 " + " · ".join(res))
    return "\n".join(lines)


def weekly_stats(stats: dict) -> str:
    return (
        "📊 <b>HAFTALIK HISOBOT</b>\n\n"
        f"Yopilgan: <b>{stats['closed']}</b> · Yutuq: <b>{stats['wins']}</b> "
        f"({stats['win_rate']}%)\n"
        f"Jami natija: <b>{stats['total_r']:+.2f}R</b> · Ochiq: {stats['open']}")

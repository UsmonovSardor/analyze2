"""Notifier — turns runtime events into Telegram messages (SRS doc 23).

CRITICAL (carry-over lesson from the old bot): the command poller MUST reject any
message whose chat id is not the configured allowlist. The old bot accepted
commands from anyone who found it; BLACK LION only answers its own group.
"""
from __future__ import annotations

from ..core.logging import get_logger
from ..engines.rule_engine import Signal
from ..journal import Journal, TradeRow
from . import format as fmt
from .chart import render_signal_chart
from .client import TelegramClient

log = get_logger("telegram.notifier")


class Notifier:
    def __init__(self, client: TelegramClient | None = None,
                 health_provider=None) -> None:
        self.client = client or TelegramClient()
        self.health_provider = health_provider   # callable → HealthReport (optional)
        self._offset = 0
        self.trade_executor = None    # callable(sid)->str, set by Runtime (button)
        self.trade_enabled = False    # show the Avto-savdo button only in trade modes

    @property
    def enabled(self) -> bool:
        return self.client.configured

    # ── push events ───────────────────────────────────────────────────────
    def on_signal(self, sig: Signal, sig_id: int, df=None,
                  timeframe: str = "H1", market_ctx: str = "") -> None:
        msg = fmt.signal_message(sig, sig_id, market_ctx)
        markup = self._trade_button(sig_id) if self.trade_enabled else None
        img = render_signal_chart(sig, df, timeframe) if df is not None else None
        if img and hasattr(self.client, "send_photo"):
            self.client.send_photo(img, caption=msg, reply_markup=markup)
        else:
            self.client.send(msg, reply_markup=markup)

    def on_outcome(self, row: TradeRow, status: str, result_r: float | None = None,
                   df=None, timeframe: str = "H1") -> None:
        msg = fmt.outcome_message(row, status, result_r)
        # a TradeRow carries symbol/direction/entry/stop/tp — enough to draw the chart
        img = (render_signal_chart(row, df, timeframe or "H1", outcome=(status, result_r))
               if df is not None else None)
        if img and hasattr(self.client, "send_photo"):
            self.client.send_photo(img, caption=msg)
        else:
            self.client.send(msg)

    @staticmethod
    def _trade_button(sig_id: int) -> dict:
        return {"inline_keyboard": [[
            {"text": "🚀 Avto-savdo (demo)", "callback_data": f"trade:{sig_id}"}]]}

    def send_daily_digest(self, journal: Journal) -> None:
        text = fmt.daily_digest(journal.stats(7), journal.signals_today())
        try:                                    # per-strategy expectancy block
            from ..ai import stats_report
            text += "\n\n" + stats_report(journal.closed_rows(days=30))
        except Exception:
            pass                                # digest must never fail on stats
        self.client.send(text)

    # ── command poller (allowlisted) ──────────────────────────────────────
    def _allowed(self, chat_id) -> bool:
        """Only the configured chat may issue commands (doc 23 §11 / bot lesson)."""
        return str(chat_id) == str(self.client.chat_id)

    def poll_commands(self, journal: Journal) -> int:
        """Process pending updates; returns how many commands were handled.
        Messages from non-allowlisted chats are ignored (logged, never answered)."""
        handled = 0
        for update in self.client.get_updates(self._offset, timeout=0):
            self._offset = update["update_id"] + 1
            if "callback_query" in update:
                self._handle_callback(update["callback_query"])
                handled += 1
                continue
            msg = update.get("message", {})
            text = (msg.get("text") or "").strip()
            chat_id = msg.get("chat", {}).get("id")
            if not text.startswith("/"):
                continue
            if not self._allowed(chat_id):
                log.warning("UnauthorizedCommand", chat_id=chat_id, text=text[:40])
                continue
            self._handle(text, journal)
            handled += 1
        return handled

    def _handle_callback(self, cb: dict) -> None:
        """Handle a tapped inline button. Only the allowlisted chat may trade — a
        button press from anyone else is refused (bot-lesson allowlist)."""
        data = str(cb.get("data") or "")
        cb_id = cb.get("id", "")
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        if not self._allowed(chat_id):
            log.warning("UnauthorizedCallback", chat_id=chat_id, data=data[:40])
            self.client.answer_callback(cb_id, "⛔️ Ruxsat yo'q")
            return
        if data.startswith("trade:") and self.trade_executor is not None:
            self.client.answer_callback(cb_id, "⏳ Bajarilmoqda...")
            try:
                sid = int(data.split(":", 1)[1])
            except ValueError:
                return
            self.client.send(self.trade_executor(sid))

    def _handle(self, text: str, journal: Journal) -> None:
        cmd = text.split()[0].lstrip("/").lower().split("@")[0]
        if cmd in ("stats", "stat"):
            self.client.send(fmt.weekly_stats(journal.stats(7)))
        elif cmd in ("open", "ochiq"):
            rows = journal.open_trades()
            if not rows:
                self.client.send("📭 Ochiq savdo yo'q.")
            else:
                lines = [f"#{r.id} <b>{r.symbol}</b> · {r.direction} · {r.status}"
                         for r in rows]
                self.client.send("📂 <b>Ochiq savdolar:</b>\n" + "\n".join(lines))
        elif cmd in ("digest", "hisobot"):
            self.send_daily_digest(journal)
        elif cmd in ("health", "holat", "sogliq"):
            if self.health_provider is not None:
                self.client.send(fmt.health_message(self.health_provider()))
            else:
                self.client.send("ℹ️ Sog'liq monitoringi ulanmagan.")
        elif cmd in ("help", "start", "yordam"):
            self.client.send(
                "🦁 <b>BLACK LION AI</b>\n"
                "AI-asosli savdo signallari\n\n"
                "🚀 Har signal ostidagi <b>Avto-savdo</b> tugmasi — bosilsa bot "
                "MT5 demo'da order ochadi, stop/TP qo'yadi va o'zi boshqaradi.\n\n"
                "/stats — haftalik statistika\n"
                "/open — ochiq savdolar\n"
                "/health — bot sog'lig'i\n"
                "/digest — kunlik hisobot")

    def send_health_alert(self, report) -> None:
        self.client.send("🚨 <b>Ogohlantirish</b>\n" + fmt.health_message(report))

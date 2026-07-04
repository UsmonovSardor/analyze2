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
from .client import TelegramClient

log = get_logger("telegram.notifier")


class Notifier:
    def __init__(self, client: TelegramClient | None = None) -> None:
        self.client = client or TelegramClient()
        self._offset = 0

    @property
    def enabled(self) -> bool:
        return self.client.configured

    # ── push events ───────────────────────────────────────────────────────
    def on_signal(self, sig: Signal, sig_id: int, market_ctx: str = "") -> None:
        self.client.send(fmt.signal_message(sig, sig_id, market_ctx))

    def on_outcome(self, row: TradeRow, status: str, result_r: float | None = None) -> None:
        self.client.send(fmt.outcome_message(row, status, result_r))

    def send_daily_digest(self, journal: Journal) -> None:
        self.client.send(fmt.daily_digest(journal.stats(7), journal.signals_today()))

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
        elif cmd in ("help", "start", "yordam"):
            self.client.send(
                "🦁 <b>BLACK LION AI</b>\n"
                "AI-asosli savdo signallari (dry-run rejimida)\n\n"
                "/stats — haftalik statistika\n"
                "/open — ochiq savdolar\n"
                "/digest — kunlik hisobot")

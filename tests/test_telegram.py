"""Doc 23 test cases: message formatting + notifier + chat allowlist."""
import pytest

from blacklion.engines.rule_engine import Signal
from blacklion.journal import Journal, TradeRow
from blacklion.telegram import Notifier
from blacklion.telegram import format as fmt
from blacklion.telegram.client import TelegramClient


def sig(direction="BUY") -> Signal:
    return Signal(symbol="XAUUSD", direction=direction, entry=3400.0,
                  stop_loss=3392.0, tp1=3406.0, tp2=3416.0, tp3=3428.0, rr=2.0,
                  confidence=88, confluence_score=85, reasons=["Bullish BOS", "Fresh OB"])


# ── formatting (pure) ─────────────────────────────────────────────────────
def test_signal_message_contains_levels_and_reasons():
    m = fmt.signal_message(sig(), 7, market_ctx="XAUUSD · H1")
    assert "BUY" in m and "XAUUSD" in m and "#7" in m
    assert "3400" in m and "3392" in m and "3428" in m
    assert "Bullish BOS" in m and "Fresh OB" in m


def test_signal_message_escapes_html():
    s = sig()
    s.reasons = ["a < b & c > d"]
    m = fmt.signal_message(s, 1)
    assert "&lt;" in m and "&amp;" in m and "&gt;" in m


def test_outcome_message_shows_r():
    row = TradeRow(id=3, symbol="EURUSD", direction="BUY", entry=1.1, stop_loss=1.098,
                   tp1=1.101, tp2=1.105, tp3=1.11, status="tp3")
    m = fmt.outcome_message(row, "tp3", 2.4)
    assert "TP3" in m and "+2.40R" in m


# ── client not-configured is safe ─────────────────────────────────────────
def test_client_not_configured_logs_instead_of_raising():
    c = TelegramClient(token="", chat_id="")
    assert c.configured is False
    assert c.send("hi") is None          # no crash, returns None


# ── notifier + allowlist ──────────────────────────────────────────────────
class FakeClient:
    def __init__(self, chat_id="100"):
        self.chat_id = chat_id
        self.sent: list[str] = []
        self._updates: list[dict] = []

    @property
    def configured(self):
        return True

    def send(self, text, chat_id=None, reply_markup=None):
        self.sent.append(text)
        return 1

    def get_updates(self, offset, timeout=20):
        u, self._updates = self._updates, []
        return u


@pytest.fixture
def journal(tmp_path) -> Journal:
    return Journal(db_path=str(tmp_path / "j.db"))


def test_notifier_sends_signal():
    fc = FakeClient()
    Notifier(fc).on_signal(sig(), 9)
    assert len(fc.sent) == 1 and "#9" in fc.sent[0]


def test_command_from_wrong_chat_is_ignored(journal):
    fc = FakeClient(chat_id="100")
    fc._updates = [{"update_id": 1, "message": {"text": "/stats",
                                                "chat": {"id": 999}}}]  # NOT allowlisted
    n = Notifier(fc)
    handled = n.poll_commands(journal)
    assert handled == 0 and fc.sent == []          # ignored, never answered


def test_command_from_allowlisted_chat_is_handled(journal):
    fc = FakeClient(chat_id="100")
    fc._updates = [{"update_id": 1, "message": {"text": "/stats",
                                                "chat": {"id": 100}}}]
    n = Notifier(fc)
    handled = n.poll_commands(journal)
    assert handled == 1 and len(fc.sent) == 1 and "HAFTALIK" in fc.sent[0]


def test_health_command_uses_provider(journal):
    from blacklion.monitoring import HealthMonitor
    mon = HealthMonitor()
    mon.record_scan(signals=1, errors=0, feed_ok=True)
    fc = FakeClient(chat_id="100")
    n = Notifier(fc, health_provider=lambda: mon.snapshot(signals_today=1, open_trades=0))
    fc._updates = [{"update_id": 8, "message": {"text": "/health",
                                                "chat": {"id": 100}}}]
    n.poll_commands(journal)
    assert "HEALTHY" in fc.sent[0]


def test_open_command_lists_trades(journal):
    sid = journal.record_signal(sig())
    journal.record_execution(sid, "T-1", 0.1, 3400.0)
    fc = FakeClient(chat_id="100")
    fc._updates = [{"update_id": 5, "message": {"text": "/open",
                                                "chat": {"id": 100}}}]
    Notifier(fc).poll_commands(journal)
    assert "XAUUSD" in fc.sent[0]

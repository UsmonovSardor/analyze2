"""Doc 04 test cases: signal recording, execution linkage, outcomes, stats."""
import pytest

from blacklion.engines.rule_engine import Signal
from blacklion.journal import Journal


def sig(symbol="EURUSD", direction="BUY", entry=1.1, sl=1.098) -> Signal:
    return Signal(symbol=symbol, direction=direction, entry=entry, stop_loss=sl,
                  tp1=1.101, tp2=1.105, tp3=1.11, rr=2.5, confidence=88,
                  confluence_score=85, reasons=["BOS", "OB"])


@pytest.fixture
def journal(tmp_path) -> Journal:
    return Journal(db_path=str(tmp_path / "j.db"))


def test_record_and_read_signal(journal):
    sid = journal.record_signal(sig())
    row = journal.get(sid)
    assert row is not None and row.symbol == "EURUSD" and row.direction == "BUY"
    assert row.status == "open"


def test_execution_links_ticket(journal):
    sid = journal.record_signal(sig())
    journal.record_execution(sid, ticket="T-1", volume=0.5, fill_price=1.1001)
    assert journal.get(sid).ticket == "T-1"
    assert len(journal.open_trades()) == 1        # only ticketed trades count


def test_untraded_signal_is_shadow_tracked(journal):
    # dry-run: every signal is tracked for its forward outcome, executed or not,
    # so the AI layer gets a labelled TP/SL history
    journal.record_signal(sig())                  # recorded, never executed
    open_rows = journal.open_trades()
    assert len(open_rows) == 1 and open_rows[0].ticket is None


def test_close_updates_result_and_stats(journal):
    sid = journal.record_signal(sig())
    journal.record_execution(sid, "T-1", 0.5, 1.1001)
    journal.close_signal(sid, status="tp3", result_r=2.4)
    st = journal.stats(days=7)
    assert st["closed"] == 1 and st["wins"] == 1 and st["total_r"] == 2.4
    assert journal.get(sid).status == "tp3"


def test_realized_r_window(journal):
    for r in (2.0, -1.0, 1.5):
        sid = journal.record_signal(sig())
        journal.close_signal(sid, "tp2", r)
    assert journal.realized_r(since_seconds=86400) == 2.5


def test_signals_today_and_cooldown(journal):
    journal.record_signal(sig(symbol="XAUUSD"))
    assert journal.signals_today() == 1
    assert journal.recent_signal_for("XAUUSD", hours=3)
    assert not journal.recent_signal_for("BTCUSDT", hours=3)


def test_persists_across_instances(tmp_path):
    path = str(tmp_path / "j.db")
    j1 = Journal(db_path=path)
    sid = j1.record_signal(sig())
    j2 = Journal(db_path=path)                     # reopen
    assert j2.get(sid) is not None

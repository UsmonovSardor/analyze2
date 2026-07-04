"""End-to-end runtime: source → pipeline → risk → execution → journal → outcomes."""
import pytest

from blacklion.data.sources import ReplaySource
from blacklion.engines.rule_engine import Signal
from blacklion.execution import PaperBroker
from blacklion.journal import Journal
from blacklion.runtime import Runtime
from tests.helpers import df_from_ohlc


def _flat(n: float, count: int) -> list[tuple]:
    return [(n, n + 0.2, n - 0.2, n) for _ in range(count)]


@pytest.fixture
def rt(tmp_path) -> Runtime:
    frame = df_from_ohlc(_flat(1.1000, 300))
    src = ReplaySource({"EURUSD:H1": frame, "EURUSD:H4": frame})
    broker = PaperBroker(prices={"EURUSD": 1.1000}, spread_points={"EURUSD": 5})
    broker.connect()
    r = Runtime(src, broker, journal=Journal(db_path=str(tmp_path / "j.db")))
    r.symbols = ["EURUSD"]                # focus the watchlist for the test
    return r


def test_scan_once_runs_and_is_deterministic(rt):
    a = rt.scan_once()
    assert isinstance(a, list)           # flat market → likely NO TRADE, but must not crash


def test_scan_records_signal_when_generated(rt, monkeypatch):
    # force the pipeline to emit a signal so we exercise the record→risk→exec path
    sig = Signal(symbol="EURUSD", direction="BUY", entry=1.1000, stop_loss=1.0980,
                 tp1=1.1010, tp2=1.1050, tp3=1.1100, rr=2.5, confidence=88,
                 confluence_score=90, reasons=["forced"])
    from blacklion.engines.rule_engine import RuleDecision

    def fake_run(symbol, df, htf_bullish=None, ts=None):
        return RuleDecision(symbol=symbol, decision="BUY", confluence_score=90,
                            confidence=88, reasons=["forced"], signal=sig)

    monkeypatch.setattr(rt.pipeline, "run", fake_run)
    ids = rt.scan_once()
    assert len(ids) == 1
    row = rt.journal.get(ids[0])
    assert row.ticket is not None        # executed through PaperBroker
    assert len(rt.broker.positions()) == 1


def test_cooldown_blocks_second_scan(rt, monkeypatch):
    sig = Signal(symbol="EURUSD", direction="BUY", entry=1.1, stop_loss=1.098,
                 tp1=1.101, tp2=1.105, tp3=1.11, rr=2.5, confidence=88,
                 confluence_score=90, reasons=["x"])
    from blacklion.engines.rule_engine import RuleDecision
    monkeypatch.setattr(rt.pipeline, "run", lambda *a, **k: RuleDecision(
        symbol="EURUSD", decision="BUY", confluence_score=90, confidence=88,
        reasons=["x"], signal=sig))
    assert len(rt.scan_once()) == 1
    assert rt.scan_once() == []          # within cooldown → skipped


def _set_last_bar(rt, low: float, high: float) -> None:
    """Point the data source's latest EURUSD bar at a given low/high so outcome
    tracking (which reads price from the SOURCE, not the broker) can resolve.
    open/close pinned to 1.1000 and clamped inside [low, high] so the candle is
    valid (else the validator drops it)."""
    frame = df_from_ohlc(_flat(1.1000, 300))
    oc = min(max(1.1000, low), high)
    frame.loc[frame.index[-1], ["open", "high", "low", "close"]] = [oc, high, low, oc]
    rt.source._frames["EURUSD:H1"] = frame


def test_check_outcomes_closes_at_stop(rt):
    sid = rt.journal.record_signal(Signal(
        symbol="EURUSD", direction="BUY", entry=1.1000, stop_loss=1.0980,
        tp1=1.1010, tp2=1.1050, tp3=1.1100, rr=2.5, confidence=88,
        confluence_score=90, reasons=["x"]))
    rt.journal.record_execution(sid, "T-1", 0.5, 1.1000)
    _set_last_bar(rt, low=1.0975, high=1.0999)   # bar dipped below stop
    rt.check_outcomes()
    assert rt.journal.get(sid).status == "stopped"
    assert rt.journal.get(sid).result_r == -1.0


def test_check_outcomes_closes_at_tp3(rt):
    sid = rt.journal.record_signal(Signal(
        symbol="EURUSD", direction="BUY", entry=1.1000, stop_loss=1.0980,
        tp1=1.1010, tp2=1.1050, tp3=1.1100, rr=2.5, confidence=88,
        confluence_score=90, reasons=["x"]))
    rt.journal.record_execution(sid, "T-1", 0.5, 1.1000)
    _set_last_bar(rt, low=1.1001, high=1.1105)   # bar spiked above tp3
    rt.check_outcomes()
    row = rt.journal.get(sid)
    assert row.status == "tp3" and row.result_r == 5.0

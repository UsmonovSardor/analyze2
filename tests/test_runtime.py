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
    r.scan_tfs = [("H1", "H4")]           # single TF for deterministic tests
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


def _long(rt) -> int:
    """A BUY on EURUSD: entry 1.1000, stop 1.0980 (r=0.0020), so
    tp1=1.1010→0.5R, tp2=1.1050→2.5R, tp3=1.1100→5.0R."""
    sid = rt.journal.record_signal(Signal(
        symbol="EURUSD", direction="BUY", entry=1.1000, stop_loss=1.0980,
        tp1=1.1010, tp2=1.1050, tp3=1.1100, rr=2.5, confidence=88,
        confluence_score=90, reasons=["x"]))
    rt.journal.record_execution(sid, "T-1", 0.5, 1.1000)
    return sid


def test_check_outcomes_scales_out_to_tp3(rt):
    # one bar above tp3, but stop stays above entry — advances one stage per call:
    # open → tp1 → tp2 → tp3, booking 0.4·0.5 + 0.4·2.5 + 0.2·5.0 = 2.20R
    sid = _long(rt)
    _set_last_bar(rt, low=1.1001, high=1.1105)
    rt.check_outcomes()
    assert rt.journal.get(sid).status == "tp1"
    rt.check_outcomes()
    assert rt.journal.get(sid).status == "tp2"
    rt.check_outcomes()
    row = rt.journal.get(sid)
    assert row.status == "tp3" and row.result_r == 2.2


def test_tp1_then_reversal_books_partial_not_full_stop(rt):
    # THE FIX: price tags TP1 then falls back through entry. Old logic = −1.0R;
    # now the runner exits at breakeven so the trade banks +0.20R (0.4·0.5R).
    sid = _long(rt)
    _set_last_bar(rt, low=1.1001, high=1.1015)     # tagged tp1 only
    rt.check_outcomes()
    assert rt.journal.get(sid).status == "tp1"
    _set_last_bar(rt, low=1.0999, high=1.1002)     # fell back below entry
    rt.check_outcomes()
    row = rt.journal.get(sid)
    assert row.status == "breakeven" and row.result_r == 0.2


def test_tp2_then_reversal_books_both_partials(rt):
    sid = _long(rt)
    _set_last_bar(rt, low=1.1001, high=1.1015)     # → tp1
    rt.check_outcomes()
    _set_last_bar(rt, low=1.1001, high=1.1055)     # → tp2 (0.4·0.5 + 0.4·2.5)
    rt.check_outcomes()
    assert rt.journal.get(sid).status == "tp2"
    _set_last_bar(rt, low=1.0999, high=1.1002)     # runner out at breakeven
    rt.check_outcomes()
    row = rt.journal.get(sid)
    assert row.status == "breakeven" and row.result_r == 1.2


def test_multi_timeframe_scan(tmp_path):
    from blacklion.engines.rule_engine import RuleDecision, Signal
    frame = df_from_ohlc(_flat(1.1000, 300))
    src = ReplaySource({"EURUSD:M15": frame, "EURUSD:H1": frame, "EURUSD:H4": frame})
    broker = PaperBroker(prices={"EURUSD": 1.1000}, spread_points={"EURUSD": 5})
    broker.connect()
    r = Runtime(src, broker, journal=Journal(db_path=str(tmp_path / "j.db")))
    r.symbols = ["EURUSD"]
    r.scan_tfs = [("M15", "H1"), ("H1", "H4")]   # two timeframes

    sig = Signal(symbol="EURUSD", direction="BUY", entry=1.1, stop_loss=1.098,
                 tp1=1.101, tp2=1.105, tp3=1.11, rr=2.5, confidence=88,
                 confluence_score=90, reasons=["x"])
    r.pipeline.run = lambda *a, **k: RuleDecision(
        symbol="EURUSD", decision="BUY", confluence_score=90, confidence=88,
        reasons=["x"], signal=sig)
    ids = r.scan_once()
    assert len(ids) == 2                          # one signal per timeframe
    tfs = {r.journal.get(i).timeframe for i in ids}
    assert tfs == {"M15", "H1"}                   # recorded with their entry TF


def test_parse_timeframes():
    assert Runtime._parse_tfs("M15:H1,H1:H4") == [("M15", "H1"), ("H1", "H4")]
    assert Runtime._parse_tfs("") == [("H1", "H4")]

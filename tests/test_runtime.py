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


def test_low_confidence_signal_is_shadowed_not_published(rt, monkeypatch):
    """Publish tier: a signal below minimum_publish_confidence is journaled
    (labelled ML data) but never sent to Telegram and never auto-traded."""
    sig = Signal(symbol="EURUSD", direction="BUY", entry=1.1000, stop_loss=1.0980,
                 tp1=1.1010, tp2=1.1050, tp3=1.1100, rr=2.5, confidence=62,
                 confluence_score=66, reasons=["weak"])
    from blacklion.engines.rule_engine import RuleDecision
    monkeypatch.setattr(rt.pipeline, "run", lambda *a, **k: RuleDecision(
        symbol="EURUSD", decision="BUY", confluence_score=66, confidence=62,
        reasons=["weak"], signal=sig))
    published = []
    monkeypatch.setattr(rt.notifier, "on_signal",
                        lambda *a, **k: published.append(a))
    ids = rt.scan_once()
    assert len(ids) == 1                      # journaled → ML candidate
    assert published == []                    # NOT sent to the group
    assert rt.journal.get(ids[0]).ticket is None   # NOT auto-traded
    assert rt.broker.positions() == []


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


def test_tp2_runner_trails_atr_and_locks_profit(rt):
    """P4: after TP2 the runner trails 1×ATR behind price instead of sitting at
    breakeven — a reversal closes it IN PROFIT ("trailed"), never back at 0."""
    sid = _long(rt)
    _set_last_bar(rt, low=1.1001, high=1.1015)     # → tp1
    rt.check_outcomes()
    _set_last_bar(rt, low=1.1001, high=1.1055)     # → tp2
    rt.check_outcomes()
    assert rt.journal.get(sid).status == "tp2"
    # runner spikes far above (flat-frame ATR ≈ 0.40) then the same bar's low
    # tags the trailed stop (≈ high − ATR) — the runner exits in profit
    _set_last_bar(rt, low=1.19, high=1.60)
    rt.check_outcomes()
    row = rt.journal.get(sid)
    assert row.status == "trailed"
    assert row.result_r > 1.2                      # strictly better than breakeven


def test_opposite_choch_exits_early_before_stop(rt, monkeypatch):
    """P4: an opposite CHOCH while the trade is open closes it at market —
    a small controlled loss instead of riding to the full −1R stop."""
    from types import SimpleNamespace
    sid = _long(rt)
    _set_last_bar(rt, low=1.0995, high=1.1005)     # neither TP nor stop touched
    monkeypatch.setattr(rt.structure, "analyze", lambda *a, **k: SimpleNamespace(
        choch=True, choch_direction="bearish"))
    rt.check_outcomes()
    row = rt.journal.get(sid)
    assert row.status == "invalidated"
    assert row.result_r is not None and -1.0 < row.result_r <= 0.05


def test_time_stop_closes_stale_trade(rt, monkeypatch):
    """P4: N bars without progress → exit as 'stale' instead of tying up risk."""
    import time as _t
    from types import SimpleNamespace
    sid = _long(rt)
    with rt.journal._conn() as c:                  # age the trade 13 H1 bars
        c.execute("UPDATE signals SET created_at=? WHERE id=?",
                  (int(_t.time()) - 13 * 3600, sid))
    _set_last_bar(rt, low=1.0995, high=1.1005)     # never reached +0.5R
    monkeypatch.setattr(rt.structure, "analyze", lambda *a, **k: SimpleNamespace(
        choch=False, choch_direction=""))          # isolate the time-stop rule
    rt.check_outcomes()
    row = rt.journal.get(sid)
    assert row.status == "stale"
    assert row.result_r is not None and -1.0 < row.result_r <= 0.05


def test_execute_signal_opens_and_is_idempotent(rt):
    sid = rt.journal.record_signal(Signal(
        symbol="EURUSD", direction="BUY", entry=1.1000, stop_loss=1.0980,
        tp1=1.1010, tp2=1.1050, tp3=1.1100, rr=2.5, confidence=88,
        confluence_score=90, reasons=["x"]))
    msg = rt.execute_signal(sid)
    assert "Order ochildi" in msg
    assert rt.journal.get(sid).ticket is not None           # opened through broker
    assert "allaqachon" in rt.execute_signal(sid)           # second tap is a no-op


def test_manual_mode_scan_signals_but_does_not_trade(rt, monkeypatch):
    rt.auto_execute = False
    sig = Signal(symbol="EURUSD", direction="BUY", entry=1.1, stop_loss=1.098,
                 tp1=1.101, tp2=1.105, tp3=1.11, rr=2.5, confidence=88,
                 confluence_score=90, reasons=["x"])
    from blacklion.engines.rule_engine import RuleDecision
    monkeypatch.setattr(rt.pipeline, "run", lambda *a, **k: RuleDecision(
        symbol="EURUSD", decision="BUY", confluence_score=90, confidence=88,
        reasons=["x"], signal=sig))
    ids = rt.scan_once()
    assert len(ids) == 1                                     # signalled…
    assert rt.journal.get(ids[0]).ticket is None            # …but NOT auto-traded


def _flood_shadow_book(rt) -> None:
    """Fill the journal with the kind of shadow book that blocked the first live
    trade: many never-filled open signals + a big paper realized loss, none of
    which ever became a real broker order (no ticket)."""
    for _ in range(18):
        rt.journal.record_signal(Signal(
            symbol="EURUSD", direction="BUY", entry=1.1, stop_loss=1.098,
            tp1=1.101, tp2=1.105, tp3=1.11, rr=2.5, confidence=88,
            confluence_score=90, reasons=["shadow"]))
    for _ in range(18):                       # −18R of paper losses, all shadow
        sid = rt.journal.record_signal(Signal(
            symbol="GBPUSD", direction="SELL", entry=1.3, stop_loss=1.302,
            tp1=1.299, tp2=1.295, tp3=1.29, rr=2.5, confidence=88,
            confluence_score=90, reasons=["shadow"]))
        rt.journal.close_signal(sid, "stopped", -1.0)


def test_trade_mode_risk_uses_real_broker_not_shadow_book(rt):
    # mt5-manual: the button is live but the scanner does not auto-trade.
    rt.auto_execute = False
    rt.notifier.trade_enabled = True
    _flood_shadow_book(rt)                     # 18 open + −18R shadow, zero real fills

    sid = rt.journal.record_signal(Signal(
        symbol="EURUSD", direction="BUY", entry=1.1000, stop_loss=1.0980,
        tp1=1.1010, tp2=1.1050, tp3=1.1100, rr=2.5, confidence=88,
        confluence_score=90, reasons=["x"]))
    # Real broker is flat → risk approves despite the flooded shadow book.
    assert rt.broker.positions() == []
    msg = rt.execute_signal(sid)
    assert "Order ochildi" in msg
    assert rt.journal.get(sid).ticket is not None


def test_shadow_mode_still_blocks_on_shadow_book(rt):
    # Dry-run (paper / mt5-data): no order can be placed, so the shadow book
    # governs risk and the over-exposed account (18 opens, −18R) must veto.
    rt.auto_execute = False
    rt.notifier.trade_enabled = False
    _flood_shadow_book(rt)
    sig = Signal(symbol="EURUSD", direction="BUY", entry=1.1, stop_loss=1.098,
                 tp1=1.101, tp2=1.105, tp3=1.11, rr=2.5, confidence=88,
                 confluence_score=90, reasons=["x"])
    d = rt.risk.evaluate(sig, rt._account_state())
    assert not d.approved                      # shadow caps still bite in dry-run


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

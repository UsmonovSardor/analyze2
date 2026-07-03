"""Doc 19 test cases: pre-validation, execution, slippage guard, partial close,
breakeven, position sync — all against the deterministic PaperBroker."""
import pytest

from blacklion.engines.rule_engine import Signal
from blacklion.execution import ExecutionEngine, PaperBroker
from blacklion.risk import RiskDecision


def signal(symbol="EURUSD", direction="BUY", entry=1.1000, sl=1.0980, tp2=1.1050) -> Signal:
    return Signal(symbol=symbol, direction=direction, entry=entry, stop_loss=sl,
                  tp1=(entry + tp2) / 2, tp2=tp2, tp3=entry + (tp2 - entry) * 2,
                  rr=2.5, confidence=88, confluence_score=85, reasons=["t"])


def approved(lot=0.5) -> RiskDecision:
    return RiskDecision(approved=True, lot_size=lot, risk_pct=1.0, rr=2.5, risk_grade="LOW")


@pytest.fixture
def broker() -> PaperBroker:
    b = PaperBroker(prices={"EURUSD": 1.1000}, spread_points={"EURUSD": 8})
    b.connect()
    return b


def test_execute_places_order(broker):
    eng = ExecutionEngine(broker)
    res = eng.execute(signal(), approved())
    assert res.status == "EXECUTED"
    assert res.ticket and res.volume == 0.5
    assert len(broker.positions()) == 1


def test_rejects_when_risk_not_approved(broker):
    eng = ExecutionEngine(broker)
    res = eng.execute(signal(), RiskDecision(approved=False, reasons=["x"]))
    assert res.status == "REJECTED"
    assert not broker.positions()


def test_rejects_when_not_connected():
    b = PaperBroker(prices={"EURUSD": 1.1})       # not connected
    res = ExecutionEngine(b).execute(signal(), approved())
    assert res.status == "REJECTED" and "connected" in res.reason


def test_rejects_when_market_closed(broker):
    broker.set_market_closed(True)
    res = ExecutionEngine(broker).execute(signal(), approved())
    assert res.status == "REJECTED" and "closed" in res.reason


def test_rejects_when_spread_too_wide(broker):
    broker._spreads["EURUSD"] = 50           # cap is 15 in symbols.yaml
    res = ExecutionEngine(broker).execute(signal(), approved())
    assert res.status == "REJECTED" and "spread" in res.reason


def test_slippage_guard_unwinds(broker):
    broker._slip = 0.0010                     # 0.0010 fill slippage
    eng = ExecutionEngine(broker, max_slippage_points={"EURUSD": 0.0005})
    res = eng.execute(signal(), approved())
    assert res.status == "FAILED" and "slippage" in res.reason
    assert not broker.positions()             # position was closed back out


def test_partial_close_reduces_volume(broker):
    eng = ExecutionEngine(broker)
    res = eng.execute(signal(), approved(lot=1.0))
    part = eng.partial_close(res.ticket, 0.4)
    assert part.ok and abs(part.volume - 0.4) < 1e-9
    assert abs(broker.positions()[0].volume - 0.6) < 1e-9


def test_move_to_breakeven(broker):
    eng = ExecutionEngine(broker)
    res = eng.execute(signal(entry=1.1000, sl=1.0980), approved())
    assert eng.move_to_breakeven(res.ticket, 1.1000)
    assert broker.positions()[0].stop_loss == 1.1000


def test_sync_returns_open_tickets(broker):
    eng = ExecutionEngine(broker)
    t1 = eng.execute(signal(), approved()).ticket
    assert eng.sync() == [t1]


def test_retry_then_success(monkeypatch, broker):
    eng = ExecutionEngine(broker, max_retries=3)
    calls = {"n": 0}
    real = broker.place_order

    def flaky(req):
        calls["n"] += 1
        if calls["n"] < 2:
            from blacklion.execution.broker import OrderResult
            return OrderResult(ok=False, error="timeout")
        return real(req)

    monkeypatch.setattr(broker, "place_order", flaky)
    monkeypatch.setattr("blacklion.execution.engine.time.sleep", lambda *_: None)
    res = eng.execute(signal(), approved())
    assert res.status == "EXECUTED" and calls["n"] == 2

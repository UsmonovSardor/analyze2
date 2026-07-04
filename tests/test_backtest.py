"""Doc 20 test cases: metrics purity + forward-simulation correctness + e2e run."""
from blacklion.backtest import Backtester, compute_metrics
from blacklion.engines.rule_engine import Signal
from tests.helpers import df_from_ohlc


# ── metrics (pure) ─────────────────────────────────────────────────────────
def test_metrics_empty():
    m = compute_metrics([])
    assert m.trades == 0 and m.net_r == 0 and m.profit_factor == 0


def test_metrics_basic_counts_and_pf():
    m = compute_metrics([2.0, -1.0, 1.0, -1.0])     # 2 win / 2 loss
    assert m.trades == 4 and m.wins == 2 and m.losses == 2
    assert m.win_rate == 50.0
    assert m.net_r == 1.0 and m.expectancy == 0.25
    assert m.profit_factor == 1.5                    # 3.0 gross win / 2.0 gross loss


def test_metrics_max_drawdown():
    # cumulative: 2, 1, -1, 2 → peak 2 then trough -1 ⇒ dd = -3
    m = compute_metrics([2.0, -1.0, -2.0, 3.0])
    assert m.max_drawdown_r == -3.0


def test_metrics_all_wins_profit_factor_capped():
    m = compute_metrics([1.0, 2.0])
    assert m.profit_factor == 999.0 and m.losses == 0


# ── forward simulation ──────────────────────────────────────────────────────
def _sig(direction="BUY", e=100.0, sl=98.0, tp1=103.0, tp2=104.0, tp3=108.0) -> Signal:
    return Signal(symbol="T", direction=direction, entry=e, stop_loss=sl,
                  tp1=tp1, tp2=tp2, tp3=tp3, rr=2.0, confidence=88,
                  confluence_score=85, reasons=["x"])


def _bars(seq: list[tuple]) -> "any":
    # entry bar at index 0 (flat), then future bars from seq
    rows = [(100.0, 100.1, 99.9, 100.0)] + list(seq)
    return df_from_ohlc(rows)


def test_simulate_full_win_tp3():
    bt = Backtester()
    # price marches up through tp1(103), tp2(104), tp3(108)
    df = _bars([(100, 103.5, 100, 103.2), (103, 104.5, 103, 104.2),
                (104, 108.5, 104, 108.2)])
    res = bt._simulate("T", df, 0, _sig())
    assert res.outcome == "tp3"
    # 0.4*(3/2) + 0.4*(4/2) + 0.2*(8/2) = 0.6 + 0.8 + 0.8 = 2.2R
    assert abs(res.result_r - 2.2) < 1e-6


def test_simulate_full_loss_stop_before_tp1():
    bt = Backtester()
    df = _bars([(100, 100.5, 97.5, 98.0)])          # drops straight to stop 98
    res = bt._simulate("T", df, 0, _sig())
    assert res.outcome == "stopped" and res.result_r == -1.0


def test_simulate_breakeven_after_tp1():
    bt = Backtester()
    # hits tp1 (103), then falls back to entry (breakeven stop)
    df = _bars([(100, 103.2, 100, 103.1), (103, 103.2, 99.5, 100.0)])
    res = bt._simulate("T", df, 0, _sig())
    assert res.outcome == "breakeven"
    # 0.4*(3/2) + 0.6*0 = 0.6R
    assert abs(res.result_r - 0.6) < 1e-6


def test_simulate_short_win():
    bt = Backtester()
    sig = _sig(direction="SELL", e=100.0, sl=102.0, tp1=97.0, tp2=96.0, tp3=92.0)
    df = _bars([(100, 100, 96.5, 97.0), (97, 97, 95.5, 96.0), (96, 96, 91.5, 92.0)])
    res = bt._simulate("T", df, 0, sig)
    assert res.outcome == "tp3" and res.result_r > 0


# ── end-to-end (flat market → no trades, no crash) ──────────────────────────
def test_backtest_run_flat_market():
    bt = Backtester(warmup=60)
    df = df_from_ohlc([(100, 100.2, 99.8, 100.0) for _ in range(200)])
    report = bt.run("EURUSD", df)
    assert report.bars == 200
    assert isinstance(report.trades, list)
    assert report.metrics.trades == len(report.trades)


def test_backtest_deterministic():
    bt = Backtester(warmup=60)
    df = df_from_ohlc([(100 + i * 0.1, 100 + i * 0.1 + 0.3, 100 + i * 0.1 - 0.3,
                        100 + i * 0.1) for i in range(200)])
    a = bt.run("XAUUSD", df)
    b = bt.run("XAUUSD", df)
    assert a.model_dump() == b.model_dump()

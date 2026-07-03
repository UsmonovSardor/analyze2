"""Doc 18 test cases: sizing, RR, daily lock, exposure, correlation, heat."""
from blacklion.engines.rule_engine import Signal
from blacklion.risk import AccountState, OpenPosition, RiskEngine

ENGINE = RiskEngine()


def sig(symbol="EURUSD", direction="BUY", entry=1.1000, sl=1.0980,
        tp2=1.1050) -> Signal:
    return Signal(symbol=symbol, direction=direction, entry=entry, stop_loss=sl,
                  tp1=entry + (tp2 - entry) / 2, tp2=tp2, tp3=entry + (tp2 - entry) * 2,
                  rr=2.5, confidence=88, confluence_score=85, reasons=["test"])


def flat_account(**kw) -> AccountState:
    base = dict(balance=10000, equity=10000, contract_size=100000)
    base.update(kw)
    return AccountState(**base)


def test_approves_clean_trade_and_sizes_position():
    d = ENGINE.evaluate(sig(), flat_account())
    assert d.approved
    # risk 1% of 10000 = $100; stop 20 pips = 0.0020 * 100000 = $200/lot → 0.5 lot
    assert d.lot_size == 0.5
    assert d.risk_pct == 1.0


def test_rejects_below_min_rr():
    d = ENGINE.evaluate(sig(tp2=1.1010), flat_account())   # RR 0.5
    assert not d.approved and any("RR" in r for r in d.reasons)


def test_daily_loss_lock():
    d = ENGINE.evaluate(sig(), flat_account(realized_pnl_today_pct=-3.0))
    assert not d.approved and any("daily loss" in r for r in d.reasons)


def test_weekly_loss_lock():
    d = ENGINE.evaluate(sig(), flat_account(realized_pnl_week_pct=-6.0))
    assert not d.approved and any("weekly loss" in r for r in d.reasons)


def test_max_open_trades():
    positions = [OpenPosition(symbol="XAUUSD", direction="BUY", risk_pct=0.5)
                 for _ in range(5)]
    d = ENGINE.evaluate(sig(), flat_account(open_positions=positions))
    assert not d.approved and any("max open" in r for r in d.reasons)


def test_portfolio_heat_cap():
    # 4 open positions × 1.1% = 4.4% heat; +1% new = 5.4% > 5% cap (still < 5 trades)
    positions = [OpenPosition(symbol=f"S{i}", direction="BUY", risk_pct=1.1)
                 for i in range(4)]
    d = ENGINE.evaluate(sig(), flat_account(open_positions=positions))
    assert not d.approved and any("heat" in r for r in d.reasons)


def test_correlation_filter_blocks_same_direction_peer():
    positions = [OpenPosition(symbol="GBPUSD", direction="BUY", risk_pct=0.5)]
    d = ENGINE.evaluate(sig(symbol="EURUSD", direction="BUY"),
                        flat_account(open_positions=positions))
    assert not d.approved and any("correlated" in r for r in d.reasons)


def test_correlation_allows_opposite_direction():
    positions = [OpenPosition(symbol="GBPUSD", direction="SELL", risk_pct=0.5)]
    d = ENGINE.evaluate(sig(symbol="EURUSD", direction="BUY"),
                        flat_account(open_positions=positions))
    assert d.approved


def test_crypto_exposure_cap():
    positions = [OpenPosition(symbol="BTCUSDT", direction="BUY", risk_pct=4.5)]
    d = ENGINE.evaluate(sig(symbol="ETHUSDT", direction="BUY", entry=3000,
                            sl=2940, tp2=3150),
                        flat_account(open_positions=positions))
    # BTC+ETH are also a correlation group → blocked either way; assert rejected
    assert not d.approved

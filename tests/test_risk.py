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


def test_metal_contract_sizes_real_lot_not_zero():
    """The live bug: XAUUSD sized with the FX contract (100000) computed
    0.0002 → 0.00 lots and every gold button-tap was vetoed with a bare
    "risk not approved". With the metal contract (100/lot) the same trade
    sizes to a tradeable 0.20 lots."""
    gold = sig(symbol="XAUUSD", direction="SELL",
               entry=4108.63, sl=4158.24, tp2=4009.41)
    account = flat_account(balance=100000,
                           contract_sizes={"XAUUSD": 100.0})
    d = ENGINE.evaluate(gold, account)
    assert d.approved
    # risk 1% of 100k = $1000; stop 49.61 × 100/lot = $4961/lot → 0.20 lots
    assert d.lot_size == 0.2


def test_unsizeable_lot_vetoed_with_explicit_reason():
    """Same gold trade sized with the WRONG (FX) contract must not silently
    approve a 0.0 lot — it must veto with a reason naming lot/stop/contract."""
    gold = sig(symbol="XAUUSD", direction="SELL",
               entry=4108.63, sl=4158.24, tp2=4009.41)
    d = ENGINE.evaluate(gold, flat_account(balance=100000))   # FX contract fallback
    assert not d.approved
    assert any("lot" in r and "min" in r for r in d.reasons)


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


def test_consecutive_loss_lock():
    d = ENGINE.evaluate(sig(), flat_account(consecutive_losses=3))
    assert not d.approved and any("ketma-ket" in r for r in d.reasons)


def test_consecutive_loss_under_limit_ok():
    d = ENGINE.evaluate(sig(), flat_account(consecutive_losses=2))
    assert d.approved

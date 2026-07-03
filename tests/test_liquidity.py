"""Doc 11 test cases: equal highs/lows pools, BSL/SSL, sweep detection."""
from blacklion.engines.liquidity import LiquidityEngine
from blacklion.engines.market_structure import Swing
from tests.helpers import df_from_closes, zigzag

ENGINE = LiquidityEngine()


def test_equal_highs_form_buy_side_pool():
    df = df_from_closes(zigzag([100, 110, 105, 118, 112, 127]))
    # two near-equal swing highs → a BSL pool
    swings = [Swing(1, 120.0, "high"), Swing(10, 120.05, "high"), Swing(5, 110.0, "low")]
    res = ENGINE.analyze("TEST", df, swings)
    assert res.buy_side_liquidity
    assert any(p.side == "buy" and p.touches >= 2 for p in res.pools)


def test_equal_lows_form_sell_side_pool():
    df = df_from_closes(zigzag([120, 108, 114, 100]))
    swings = [Swing(2, 100.0, "low"), Swing(8, 100.04, "low"), Swing(5, 115.0, "high")]
    res = ENGINE.analyze("TEST", df, swings)
    assert res.sell_side_liquidity
    assert any(p.side == "sell" and p.touches >= 2 for p in res.pools)


def test_sell_side_sweep_detected():
    # last candle wicks below an SSL pool then closes back above it
    closes = zigzag([110, 100, 106, 100]) + [104.0]
    df = df_from_closes(closes)
    df.loc[df.index[-1], ["open", "high", "low", "close"]] = [103.0, 105.0, 98.5, 104.0]
    swings = [Swing(2, 99.0, "low"), Swing(8, 99.05, "low"), Swing(5, 110.0, "high")]
    res = ENGINE.analyze("TEST", df, swings)
    assert res.liquidity_swept and res.sweep_direction == "bullish"


def test_no_pool_when_touches_below_minimum():
    df = df_from_closes(zigzag([100, 110, 105]))
    swings = [Swing(1, 120.0, "high"), Swing(5, 100.0, "low")]  # single of each
    res = ENGINE.analyze("TEST", df, swings)
    assert not res.buy_side_liquidity and not res.sell_side_liquidity

"""Doc 14 test cases: premium/discount, OTE, kill zones."""
from datetime import datetime, timezone

from blacklion.engines.ict import ICTEngine
from blacklion.engines.market_structure import Swing
from tests.helpers import df_from_closes

ENGINE = ICTEngine()


def test_discount_zone_below_equilibrium():
    df = df_from_closes([100, 102, 101, 103])          # close ~103 within range 100-120
    df.loc[df.index[-1], "close"] = 104.0
    swings = [Swing(0, 120.0, "high"), Swing(1, 100.0, "low")]  # eq = 110
    res = ENGINE.analyze("TEST", df, swings, trend_bullish=True)
    assert res.premium_discount == "Discount"


def test_premium_zone_above_equilibrium():
    df = df_from_closes([115, 116, 117, 118])
    swings = [Swing(0, 120.0, "high"), Swing(1, 100.0, "low")]
    res = ENGINE.analyze("TEST", df, swings, trend_bullish=False)
    assert res.premium_discount == "Premium"


def test_ote_zone_for_bullish_retracement():
    # up-leg 100→120, OTE for a long sits ~ 104.2–107.6 (62–79% back from the high)
    df = df_from_closes([120, 112, 106])
    df.loc[df.index[-1], "close"] = 105.5
    swings = [Swing(0, 120.0, "high"), Swing(1, 100.0, "low")]
    res = ENGINE.analyze("TEST", df, swings, trend_bullish=True)
    assert res.ote_zone is not None
    lo, hi = res.ote_zone
    assert lo < 105.5 < hi
    assert res.ote


def test_kill_zone_detection():
    df = df_from_closes([100, 101, 102])
    swings = [Swing(0, 120.0, "high"), Swing(1, 100.0, "low")]
    ts = datetime(2026, 7, 3, 8, 30, tzinfo=timezone.utc)   # 08:30 UTC → London kill zone
    res = ENGINE.analyze("TEST", df, swings, trend_bullish=True, ts=ts)
    assert res.kill_zone == "london"


def test_no_kill_zone_outside_windows():
    df = df_from_closes([100, 101, 102])
    swings = [Swing(0, 120.0, "high"), Swing(1, 100.0, "low")]
    ts = datetime(2026, 7, 3, 5, 0, tzinfo=timezone.utc)
    res = ENGINE.analyze("TEST", df, swings, trend_bullish=True, ts=ts)
    assert res.kill_zone == ""

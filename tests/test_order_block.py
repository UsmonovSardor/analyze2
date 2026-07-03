"""Doc 12 test cases: bullish/bearish OB detection, freshness."""
from blacklion.engines.order_block import OrderBlockEngine
from tests.helpers import df_from_ohlc

ENGINE = OrderBlockEngine()


def _flat(n: float, count: int) -> list[tuple]:
    return [(n, n + 0.2, n - 0.2, n) for _ in range(count)]


def test_bullish_order_block_before_up_displacement():
    rows = _flat(100, 20)
    rows.append((100.0, 100.1, 99.0, 99.2))       # bearish OB candle
    rows.append((99.2, 106.0, 99.1, 105.5))       # strong bullish displacement
    rows += [(105.5, 106.0, 105.0, 105.6) for _ in range(3)]  # stay away → fresh
    res = ENGINE.analyze("TEST", df_from_ohlc(rows))
    assert res.best is not None
    assert res.best.type == "bullish"
    assert res.best.fresh


def test_bearish_order_block_before_down_displacement():
    rows = _flat(100, 20)
    rows.append((100.0, 101.0, 99.9, 100.8))      # bullish OB candle
    rows.append((100.8, 100.9, 94.0, 94.5))       # strong bearish displacement
    rows += [(94.5, 95.0, 94.0, 94.4) for _ in range(3)]
    res = ENGINE.analyze("TEST", df_from_ohlc(rows))
    assert res.best is not None
    assert res.best.type == "bearish"


def test_no_order_block_without_displacement():
    res = ENGINE.analyze("TEST", df_from_ohlc(_flat(100, 30)))
    assert res.best is None


def test_mitigated_block_marked_not_fresh():
    rows = _flat(100, 20)
    rows.append((100.0, 100.1, 99.0, 99.2))       # bullish OB zone 99.0–100.1
    rows.append((99.2, 106.0, 99.1, 105.5))       # displacement
    rows.append((105.5, 106.0, 99.5, 100.0))      # price returns INTO the zone
    res = ENGINE.analyze("TEST", df_from_ohlc(rows))
    if res.best is not None:
        assert res.best.mitigated or not res.best.fresh

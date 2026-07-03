"""Doc 13 test cases: bullish/bearish FVG detection, fill tracking."""
from blacklion.engines.fvg import FVGEngine
from tests.helpers import df_from_ohlc

ENGINE = FVGEngine()


def _flat(n: float, count: int) -> list[tuple]:
    return [(n, n + 0.2, n - 0.2, n) for _ in range(count)]


def test_bullish_fvg_detected():
    rows = _flat(100, 20)
    rows.append((100.0, 100.5, 99.8, 100.2))      # candle 1 (high 100.5)
    rows.append((100.2, 104.0, 100.1, 103.8))     # displacement
    rows.append((103.8, 104.5, 101.5, 104.0))     # candle 3 (low 101.5) > c1 high
    rows += _flat(104, 3)
    res = ENGINE.analyze("TEST", df_from_ohlc(rows))
    assert res.nearest is not None and res.nearest.type == "bullish"
    assert res.nearest.gap_low <= 101.5 and res.nearest.gap_high >= 100.5 - 0.01


def test_bearish_fvg_detected():
    rows = _flat(100, 20)
    rows.append((100.0, 100.2, 99.5, 99.8))       # candle 1 (low 99.5)
    rows.append((99.8, 99.9, 96.0, 96.2))         # displacement down
    rows.append((96.2, 98.5, 95.8, 96.0))         # candle 3 (high 98.5) < c1 low
    rows += _flat(96, 3)
    res = ENGINE.analyze("TEST", df_from_ohlc(rows))
    assert res.nearest is not None and res.nearest.type == "bearish"


def test_no_fvg_in_tight_range():
    res = ENGINE.analyze("TEST", df_from_ohlc(_flat(100, 30)))
    assert res.nearest is None


def test_filled_gap_excluded_from_active():
    rows = _flat(100, 20)
    rows.append((100.0, 100.5, 99.8, 100.2))
    rows.append((100.2, 104.0, 100.1, 103.8))
    rows.append((103.8, 104.5, 101.5, 104.0))
    rows.append((104.0, 104.2, 100.0, 100.3))     # fully retraces the gap
    res = ENGINE.analyze("TEST", df_from_ohlc(rows))
    assert all(not g.filled for g in res.active)

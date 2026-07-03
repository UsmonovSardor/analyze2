"""Doc 07 test cases: invalid OHLC, timestamps, duplicates, spread, symbol."""
from datetime import datetime, timedelta, timezone

from blacklion.data.models import Candle, Timeframe
from blacklion.data.validation import detect_gap, validate_candle

TS = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)


def make(**kw) -> Candle:
    base = dict(symbol="XAUUSD", timeframe=Timeframe.M15, timestamp=TS,
                open=3398.2, high=3401.1, low=3397.4, close=3400.6,
                volume=2850, spread=18)
    base.update(kw)
    return Candle(**base)


def test_valid_candle_passes():
    assert validate_candle(make()).valid


def test_high_below_low_rejected():
    v = validate_candle(make(high=3396.0, low=3397.4, open=3396.5, close=3396.2))
    assert not v.valid and "INVALID_HIGH" in v.issues


def test_open_outside_range_rejected():
    v = validate_candle(make(open=3402.0))
    assert not v.valid and "INVALID_OPEN" in v.issues


def test_close_outside_range_rejected():
    v = validate_candle(make(close=3395.0))
    assert not v.valid and "INVALID_CLOSE" in v.issues


def test_negative_volume_rejected():
    v = validate_candle(make(volume=-5))
    assert not v.valid and "INVALID_VOLUME" in v.issues


def test_future_timestamp_rejected():
    v = validate_candle(make(timestamp=datetime.now(timezone.utc) + timedelta(hours=2)))
    assert not v.valid and "INVALID_TIMESTAMP" in v.issues


def test_misaligned_timestamp_rejected():
    v = validate_candle(make(timestamp=TS.replace(minute=7)))
    assert not v.valid and "INVALID_TIMESTAMP" in v.issues


def test_duplicate_rejected():
    v = validate_candle(make(), prev_timestamp=TS)
    assert not v.valid and "DUPLICATE_CANDLE" in v.issues


def test_out_of_order_rejected():
    v = validate_candle(make(), prev_timestamp=TS + timedelta(minutes=15))
    assert not v.valid and "INVALID_TIMESTAMP" in v.issues


def test_spread_too_high_rejected():
    v = validate_candle(make(spread=80))
    assert not v.valid and "SPREAD_TOO_HIGH" in v.issues


def test_unknown_symbol_rejected():
    v = validate_candle(make(symbol="FOOUSD"))
    assert not v.valid and "INVALID_SYMBOL" in v.issues


def test_gap_detection():
    prev = make()
    assert not detect_gap(prev, make(timestamp=TS + timedelta(minutes=15)))
    assert detect_gap(prev, make(timestamp=TS + timedelta(minutes=45)))

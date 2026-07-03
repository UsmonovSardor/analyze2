"""Doc 08 test cases: symbol mapping, UTC conversion, precision, TF aliases."""
from datetime import datetime, timezone, timedelta

import pytest

from blacklion.data.models import Timeframe
from blacklion.data.normalizer import (
    NormalizationError,
    normalize_candle,
    normalize_symbol,
    normalize_timeframe,
    normalize_timestamp,
)


def test_symbol_aliases():
    assert normalize_symbol("XAUUSD.r") == "XAUUSD"
    assert normalize_symbol("GOLD") == "XAUUSD"
    assert normalize_symbol("xauusdm") == "XAUUSD"
    assert normalize_symbol("BTCUSD") == "BTCUSDT"


def test_unknown_symbol_raises():
    with pytest.raises(NormalizationError):
        normalize_symbol("XXXYYY")


def test_timeframe_aliases():
    assert normalize_timeframe("15m") == Timeframe.M15
    assert normalize_timeframe("60") == Timeframe.H1
    assert normalize_timeframe("H4") == Timeframe.H4
    assert normalize_timeframe("1d") == Timeframe.D1
    with pytest.raises(NormalizationError):
        normalize_timeframe("7m")


def test_timestamp_to_utc():
    plus3 = datetime(2026, 7, 3, 14, 15, tzinfo=timezone(timedelta(hours=3)))
    assert normalize_timestamp(plus3) == datetime(2026, 7, 3, 11, 15, tzinfo=timezone.utc)
    with pytest.raises(NormalizationError):
        normalize_timestamp(datetime(2026, 7, 3, 14, 15))  # naive


def test_normalize_candle_precision():
    c = normalize_candle({
        "symbol": "XAUUSD.r", "timeframe": "15m",
        "timestamp": "2026-07-03T14:15:00+03:00",
        "open": 3398.123456, "high": 3401.3, "low": 3397.8, "close": 3400.649,
        "volume": 2847, "spread": 21,
    })
    assert c.symbol == "XAUUSD"
    assert c.timeframe == Timeframe.M15
    assert c.timestamp.tzinfo == timezone.utc and c.timestamp.hour == 11
    assert c.open == 3398.12          # XAUUSD digits: 2
    assert c.close == 3400.65
    assert c.volume == 2847.0

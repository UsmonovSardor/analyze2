"""Doc 06–09 test cases: indicator enrichment + ReplaySource validation."""
import pandas as pd
import pytest

from blacklion.data.indicators import add_indicators
from blacklion.data.sources import MarketDataSource, ReplaySource
from tests.helpers import df_from_closes


def test_indicators_added_and_deterministic():
    df = df_from_closes(list(range(100, 200)))[["open", "high", "low", "close", "volume"]]
    a = add_indicators(df)
    b = add_indicators(df)
    for col in ("ema20", "ema50", "ema200", "atr", "rsi", "vol_avg20"):
        assert col in a.columns
    assert a["atr"].iloc[-1] > 0
    assert (a["atr"].values == b["atr"].values).all()      # deterministic


def test_rsi_bounded_0_100():
    df = df_from_closes(list(range(100, 160)))[["open", "high", "low", "close", "volume"]]
    a = add_indicators(df)
    assert a["rsi"].dropna().between(0, 100).all()


def test_replay_source_conforms_to_protocol():
    df = df_from_closes([100, 101, 102, 103])
    src = ReplaySource({"XAUUSD:H1": df})
    assert isinstance(src, MarketDataSource)


def test_replay_source_returns_enriched_window():
    df = df_from_closes(list(range(100, 150)))
    src = ReplaySource({"EURUSD:H1": df})
    out = src.fetch("EURUSD", "H1", 20)
    assert len(out) == 20
    assert "atr" in out.columns and out["atr"].iloc[-1] > 0


def test_replay_source_drops_malformed_candles():
    good = df_from_closes([100, 101, 102, 103, 104])
    # inject a broken candle: high < low
    good.loc[2, ["high", "low"]] = [90.0, 110.0]
    src = ReplaySource({"X:H1": good})
    out = src.fetch("X", "H1", 10)
    assert (out["high"] >= out["low"]).all()               # broken row removed


def test_replay_source_missing_symbol_raises():
    src = ReplaySource({"A:H1": df_from_closes([1, 2, 3])})
    with pytest.raises(KeyError):
        src.fetch("B", "H1", 5)


def test_source_rejects_frame_missing_columns():
    src = ReplaySource({"X:H1": pd.DataFrame({"close": [1, 2, 3]})})
    with pytest.raises(ValueError):
        src.fetch("X", "H1", 3)

"""Named-strategy detectors (docs/strategies/strategy.md port): regime gate,
candle helpers, Setup A pullback, Setup B breakout + trap rejection."""
import pandas as pd

from blacklion.engines.fvg import FVGResult
from blacklion.engines.ict import ICTResult
from blacklion.engines.liquidity import LiquidityResult
from blacklion.engines.market_structure import StructureResult
from blacklion.engines.market_structure.service import Trend
from blacklion.engines.order_block import OrderBlockResult
from blacklion.engines.strategies import (DetectorContext, classify_regime,
                                          detect_all, regime_allows)
from blacklion.engines.strategies import candles
from blacklion.engines.strategies.setup_a import TrendPullback
from blacklion.engines.strategies.setup_b import RangeBreakout


def _results(symbol="EURUSD", swing_high=110.0, swing_low=100.0):
    structure = StructureResult(
        symbol=symbol, trend=Trend.BULLISH, structure="HH-HL", bos=True,
        bos_direction="bullish", choch=False, strength=75, quality="A",
        confidence=75, last_swing_high=swing_high, last_swing_low=swing_low)
    liquidity = LiquidityResult(
        symbol=symbol, buy_side_liquidity=False, sell_side_liquidity=False,
        liquidity_swept=False, liquidity_score=50, quality="B", confidence=50)
    return (structure, liquidity, OrderBlockResult(symbol=symbol),
            FVGResult(symbol=symbol),
            ICTResult(symbol=symbol, premium_discount="Discount",
                      equilibrium=105.0, ote=False, ict_score=50, quality="B"))


def _ctx(df, regime, htf_bullish=True, **overrides) -> DetectorContext:
    structure, liquidity, ob, fvg, ict = _results(**overrides)
    return DetectorContext(symbol="EURUSD", df=df, structure=structure,
                           liquidity=liquidity, order_block=ob, fvg=fvg,
                           ict=ict, htf_bullish=htf_bullish, regime=regime)


def _pullback_df(n=40) -> pd.DataFrame:
    """Uptrend that pulled back to the EMA50 with an RSI reset and a strong
    bull signal bar — a clean Setup A long."""
    base = [(103.0, 103.4, 102.8, 103.2)] * (n - 7)
    tail = [                                  # drift down into the EMA50 zone
        (106.0, 106.2, 105.4, 105.5), (105.5, 105.7, 105.0, 105.1),
        (105.1, 105.3, 104.7, 104.8), (104.8, 105.0, 104.5, 104.6),
        (104.6, 104.8, 104.3, 104.5), (104.5, 104.7, 104.2, 104.4),
        (104.3, 105.05, 104.2, 105.0),        # strong bull bar at the zone
    ]
    rows = base + tail
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df["volume"] = 100.0
    df["atr"] = 1.0
    df["ema50"] = 105.2                        # close 105.0 → 0.2×ATR away
    df["ema200"] = 100.5
    rsi = [55.0] * (n - 7) + [50, 48, 44, 42, 41, 42, 44]
    df["rsi"] = rsi
    return df


def test_setup_a_detects_clean_pullback_long():
    match = TrendPullback().detect(_ctx(_pullback_df(), "bull_pullback"))
    assert match is not None
    assert match.direction == "BUY" and match.code == "A"
    assert match.score >= 6
    assert any("EMA50 retest" in r for r in match.reasons)


def test_setup_a_rejects_deep_retrace():
    # >75% retrace of the 100→110 swing (close near 102) = trend failure
    df = _pullback_df()
    df.loc[df.index[-1], ["open", "high", "low", "close"]] = [101.3, 102.05, 101.2, 102.0]
    df["ema50"] = 102.2
    assert TrendPullback().detect(_ctx(df, "bull_pullback")) is None


def test_setup_a_rejects_wick_against():
    df = _pullback_df()
    # huge upper wick on the signal bar (absorption)
    df.loc[df.index[-1], ["open", "high", "low", "close"]] = [104.3, 107.0, 104.2, 104.6]
    assert TrendPullback().detect(_ctx(df, "bull_pullback")) is None


def _breakout_df(trap=False) -> pd.DataFrame:
    """30-bar 100–105 range, high-volume breakout close above 105, then a retest
    holding the level (or, when trap=True, a close back inside the range)."""
    rows = [(102.0, 105.0, 100.0, 102.5)] * 40           # the range
    rows += [(104.8, 106.2, 104.6, 106.0)]               # breakout bar
    after = [(106.0, 106.1, 105.6, 105.8), (105.8, 105.9, 105.4, 105.6),
             (105.6, 105.7, 105.2, 105.4)]
    if trap:
        after.append((105.4, 105.5, 104.6, 104.8))       # closes back inside
    else:
        after.append((105.15, 105.3, 105.0, 105.2))      # retest holds
    rows += after
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    vol = [100.0] * 40 + [200.0] + [90.0] * len(after)
    df["volume"] = vol
    df["atr"] = 1.0
    df["ema50"] = 104.0
    df["ema200"] = 103.0
    df["rsi"] = [55.0] * (len(rows) - 7) + [50, 48, 44, 42, 41, 42, 44]
    return df


def test_setup_b_detects_breakout_retest_long():
    match = RangeBreakout().detect(_ctx(_breakout_df(), "range", swing_high=115.0))
    assert match is not None
    assert match.direction == "BUY" and match.code == "B"
    assert match.score >= 6
    assert any("buzildi" in r for r in match.reasons)


def test_setup_b_rejects_bull_trap():
    assert RangeBreakout().detect(
        _ctx(_breakout_df(trap=True), "range", swing_high=115.0)) is None


def test_registry_returns_sorted_matches():
    matches = detect_all(_ctx(_pullback_df(), "bull_pullback"))
    assert matches and matches[0].code == "A"
    assert all(matches[i].score >= matches[i + 1].score
               for i in range(len(matches) - 1))


def test_chop_regime_detected_and_blocks_everything():
    df = _pullback_df(70)                            # regime needs ≥60 bars
    atr = [1.0] * len(df)
    atr[-1] = 5.0                                    # ATR spike >2× its average
    df["atr"] = atr
    assert classify_regime(df) == "chop"
    assert not regime_allows("chop", "BUY")
    assert not regime_allows("chop", "SELL")


def test_regime_directional_gate():
    assert regime_allows("strong_bull", "BUY")
    assert not regime_allows("strong_bull", "SELL")
    assert regime_allows("strong_bear", "SELL")
    assert not regime_allows("bear_rally", "BUY")


def test_noise_tape_produces_no_match():
    flat = pd.DataFrame([(100.0, 100.3, 99.7, 100.0)] * 60,
                        columns=["open", "high", "low", "close"])
    flat["volume"] = 100.0
    flat["atr"] = 1.0
    flat["ema50"] = 100.0
    flat["ema200"] = 100.0
    flat["rsi"] = 50.0
    assert detect_all(_ctx(flat, "range")) == []


def test_candle_helpers():
    hammer = pd.DataFrame([(100.0, 100.6, 99.8, 100.2),
                           (100.2, 100.35, 99.2, 100.3)],
                          columns=["open", "high", "low", "close"])
    assert candles.is_hammer(hammer)
    engulf = pd.DataFrame([(100.5, 100.6, 99.9, 100.0),      # bear bar
                           (99.9, 100.8, 99.8, 100.7)],      # bull engulfs it
                          columns=["open", "high", "low", "close"])
    assert candles.is_bullish_engulfing(engulf)
    assert candles.bullish_confirmation(engulf) is not None
    strong = pd.DataFrame([(100.0, 101.0, 99.9, 100.95)],
                          columns=["open", "high", "low", "close"])
    assert candles.is_strong_trend_bar(strong, "BUY")
    wick = pd.DataFrame([(100.0, 102.0, 99.9, 100.3)],
                        columns=["open", "high", "low", "close"])
    assert candles.wick_against(wick, "BUY")

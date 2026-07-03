"""Doc 10 test cases: swings, HH/HL classification, trend, BOS, CHOCH."""
import numpy as np
import pandas as pd

from blacklion.engines.market_structure import MarketStructureEngine


def make_df(closes: list[float], wick: float = 0.3) -> pd.DataFrame:
    c = np.array(closes, dtype=float)
    o = np.roll(c, 1)
    o[0] = c[0]
    high = np.maximum(o, c) + wick
    low = np.minimum(o, c) - wick
    df = pd.DataFrame({"open": o, "high": high, "low": low, "close": c,
                       "volume": 1000.0})
    tr = high - low
    df["atr"] = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean()
    return df


def zigzag(levels: list[float], leg: int = 8) -> list[float]:
    """Piecewise-linear path visiting each level — clean swing structure."""
    out: list[float] = [levels[0]]
    for a, b in zip(levels, levels[1:]):
        out += list(np.linspace(a, b, leg + 1)[1:])
    return out


ENGINE = MarketStructureEngine()


def test_uptrend_structure_and_labels():
    # rising zigzag: higher highs + higher lows
    df = make_df(zigzag([100, 110, 105, 118, 112, 127, 120, 136, 130, 146]))
    res = ENGINE.analyze("TEST", df)
    labels = [s["label"] for s in res.swings]
    assert res.trend.bullish
    assert "HH" in labels and "HL" in labels
    assert "LL" not in labels
    assert res.strength >= 50


def test_downtrend_structure():
    df = make_df(zigzag([146, 130, 136, 120, 127, 112, 118, 105, 110, 96]))
    res = ENGINE.analyze("TEST", df)
    labels = [s["label"] for s in res.swings]
    assert res.trend.bearish
    assert "LL" in labels and "LH" in labels


def test_bullish_bos_on_break_above_swing_high():
    # uptrend, then close pushes well above the last swing high
    path = zigzag([100, 110, 105, 118, 112, 127, 120]) + list(np.linspace(120, 140, 12)[1:])
    res = ENGINE.analyze("TEST", make_df(path))
    assert res.bos and res.bos_direction == "bullish"
    assert not res.choch


def test_bullish_choch_in_downtrend():
    # clear downtrend, then price reclaims the last lower-high → CHOCH, not BOS
    path = zigzag([150, 135, 141, 126, 132, 117, 123, 108]) + list(np.linspace(108, 130, 14)[1:])
    res = ENGINE.analyze("TEST", make_df(path))
    assert res.choch and res.choch_direction == "bullish"
    assert not res.bos


def test_sideways_no_bos():
    rng = np.random.default_rng(7)
    path = 100 + np.cumsum(rng.normal(0, 0.05, 120))
    res = ENGINE.analyze("TEST", make_df(list(path)))
    assert not res.bos or res.strength < 70   # no confident break in noise


def test_deterministic():
    df = make_df(zigzag([100, 110, 105, 118, 112, 127]))
    a, b = ENGINE.analyze("T", df), ENGINE.analyze("T", df)
    assert a.model_dump() == b.model_dump()

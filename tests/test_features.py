"""Doc 09 test cases: deterministic, bounded, NaN-safe feature extraction."""
import math

from blacklion.data.indicators import add_indicators
from blacklion.engines.pipeline import SignalPipeline
from blacklion.features import FeatureEngineer
from blacklion.journal import Journal
from tests.helpers import df_from_ohlc, df_from_closes, zigzag

FE = FeatureEngineer()
PIPE = SignalPipeline()


def _extract(symbol, df, direction="BUY"):
    df = add_indicators(df)                    # production feeds always enrich first
    PIPE.run(symbol, df, htf_bullish=True)     # populates PIPE.last engine outputs
    return FE.extract(symbol, df, direction=direction, **PIPE.last)


def test_features_extracted_and_finite():
    df = df_from_closes(zigzag([100, 110, 105, 118, 112, 127]))
    feats = _extract("XAUUSD", df)
    assert len(feats) >= 40                     # a rich vector
    for k, v in feats.items():
        assert isinstance(v, float)
        assert not math.isnan(v) and not math.isinf(v), k


def test_features_deterministic():
    df = df_from_closes(zigzag([100, 108, 104, 115, 110, 122]))
    a = _extract("EURUSD", df)
    b = _extract("EURUSD", df)
    assert a == b


def test_direction_flag_matches():
    df = df_from_closes(zigzag([120, 110, 114, 100]))
    assert _extract("X", df, "BUY")["direction_long"] == 1.0
    assert _extract("X", df, "SELL")["direction_long"] == 0.0


def test_key_features_present():
    df = df_from_ohlc([(100, 100.2, 99.8, 100.0) for _ in range(120)])
    feats = _extract("EURUSD", df)
    for key in ("rsi", "atr_pct", "structure_strength", "liquidity_score",
                "ict_score", "close_vs_ema200_atr", "zscore_50", "rel_volume"):
        assert key in feats


def test_flat_market_no_nan():
    df = df_from_ohlc([(1.1, 1.1002, 1.0998, 1.1) for _ in range(80)])
    feats = _extract("EURUSD", df)
    assert all(not math.isnan(v) for v in feats.values())


def test_journal_stores_and_returns_dataset(tmp_path):
    from blacklion.engines.rule_engine import Signal
    j = Journal(db_path=str(tmp_path / "j.db"))
    sig = Signal(symbol="XAUUSD", direction="BUY", entry=3400, stop_loss=3392,
                 tp1=3406, tp2=3416, tp3=3428, rr=2.0, confidence=88,
                 confluence_score=85, reasons=["x"])
    sid = j.record_signal(sig)
    j.record_features(sid, {"rsi": 55.0, "ict_score": 80.0})
    j.close_signal(sid, "tp3", 2.2)
    ds = j.features_dataset()
    assert len(ds) == 1
    feats, status, r = ds[0]
    assert feats["rsi"] == 55.0 and status == "tp3" and r == 2.2


def test_dataset_excludes_open_signals(tmp_path):
    from blacklion.engines.rule_engine import Signal
    j = Journal(db_path=str(tmp_path / "j.db"))
    sid = j.record_signal(Signal(symbol="X", direction="BUY", entry=1, stop_loss=0.9,
                                 tp1=1.1, tp2=1.2, tp3=1.3, rr=2.0, confidence=80,
                                 confluence_score=80, reasons=["x"]))
    j.record_features(sid, {"rsi": 50.0})
    assert j.features_dataset() == []           # still open → not a training row yet

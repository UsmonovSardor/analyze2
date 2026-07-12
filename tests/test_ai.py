"""ML learning layer: expectancy stats, evidence throttle, probability model
train/calibrate/promote/reject on synthetic data."""
import numpy as np
import pytest

from blacklion.ai import model as ai_model
from blacklion.ai.stats import bucket_stats, stats_report, throttled_strategies


def _row(strategy="Trend Pullback", symbol="EURUSD", tf="H1",
         status="tp3", r=2.2, pred=None) -> dict:
    return {"strategy_name": strategy, "symbol": symbol, "timeframe": tf,
            "status": status, "result_r": r, "pred_p": pred}


def test_bucket_stats_math():
    rows = [_row(r=2.2), _row(status="stopped", r=-1.0),
            _row(status="invalidated", r=-0.4), _row(status="trailed", r=1.5)]
    s = bucket_stats(rows)["Trend Pullback"]
    assert s["n"] == 4 and s["wins"] == 2
    assert s["win_rate"] == 0.5
    assert s["avg_r"] == pytest.approx(0.575)
    # 2 losers, 1 rode to the FULL stop → 50% full-stop share (P4 metric)
    assert s["full_stop_share"] == 0.5


def test_throttle_requires_evidence_then_blocks():
    losers = [_row(strategy="Range Breakout", status="stopped", r=-1.0)
              for _ in range(29)]
    assert throttled_strategies(losers, min_n=30) == set()   # n=29 → noise guard
    losers.append(_row(strategy="Range Breakout", status="stopped", r=-1.0))
    assert throttled_strategies(losers, min_n=30) == {"Range Breakout"}
    # a profitable strategy is never throttled regardless of n
    winners = [_row(r=2.0) for _ in range(50)]
    assert throttled_strategies(winners + losers, min_n=30) == {"Range Breakout"}


def test_stats_report_is_uzbek_and_valued():
    text = stats_report([_row(r=2.2), _row(status="stopped", r=-1.0)])
    assert "Trend Pullback" in text and "n=2" in text and "R" in text


def _dataset(n=400, seed=7):
    """Synthetic learnable dataset: outcome correlates with feature 'edge'."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        edge = rng.normal()
        noise = rng.normal()
        feats = {"edge": edge, "noise": noise, "const": 1.0}
        win = (edge + 0.5 * rng.normal()) > 0
        out.append((feats, "tp3" if win else "stopped", 2.0 if win else -1.0))
    return out


def test_model_trains_calibrates_and_promotes(tmp_path, monkeypatch):
    monkeypatch.setenv("BL_MODELS_DIR", str(tmp_path))
    metrics = ai_model.train(_dataset())
    assert metrics is not None and metrics["accepted"]
    assert metrics["brier"] < metrics["brier_base"]          # beats base rate
    m = ai_model.ProbabilityModel()
    p_hi = m.predict({"edge": 2.0, "noise": 0.0, "const": 1.0})
    p_lo = m.predict({"edge": -2.0, "noise": 0.0, "const": 1.0})
    assert p_hi is not None and p_lo is not None
    assert p_hi > p_lo                                       # learned the edge
    assert 0.0 <= p_lo <= 1.0 and 0.0 <= p_hi <= 1.0


def test_model_rejected_when_no_signal_in_features(tmp_path, monkeypatch):
    """Pure-noise features must NOT be promoted: validation Brier can't beat the
    base-rate baseline, so no artifact is accepted (auto-rollback by refusal)."""
    monkeypatch.setenv("BL_MODELS_DIR", str(tmp_path))
    rng = np.random.default_rng(3)
    noise = [({"a": float(rng.normal()), "b": float(rng.normal())},
              "tp3" if rng.random() > 0.5 else "stopped",
              2.0 if rng.random() > 0.5 else -1.0) for _ in range(400)]
    ai_model.train(noise)
    assert ai_model.ProbabilityModel().predict({"a": 0.0, "b": 0.0}) is None


def test_model_insufficient_samples_stays_in_collection(tmp_path, monkeypatch):
    monkeypatch.setenv("BL_MODELS_DIR", str(tmp_path))
    assert ai_model.train(_dataset(n=50)) is None            # < MIN_SAMPLES
    assert ai_model.ProbabilityModel().predict({"edge": 1.0}) is None

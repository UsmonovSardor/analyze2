"""Probability model (SRS docs 16-17) — calibrated P(profitable close).

HistGradientBoosting on the journal's 58-feature snapshots. Honest by design:
- TIME-ORDERED split (never shuffled): train on the first 75%, calibrate with
  isotonic regression and score Brier on the LAST 25% — no lookahead leakage.
- A model is ACCEPTED only if its validation Brier beats the base-rate
  baseline (always predicting the historical win-rate). Otherwise the previous
  accepted model stays live — auto-rollback by never promoting a worse one.
- Versioned artifacts in <models_dir>/model_vN.pkl + metrics.json (metrics keep
  the audit trail: n, brier vs baseline, win base-rate, feature names, ts).
- Deterministic (fixed random_state), retrained every RETRAIN_EVERY new closed
  trades once MIN_SAMPLES exist — every close makes the bot measurably smarter.

Rollout: SHADOW first (pred_p journaled per signal, no behavior change);
engines.yaml ai.mode flips to "gate" only after live shadow calibration holds.
"""
from __future__ import annotations

import json
import os
import pickle
import time

import numpy as np

from ..core import config
from ..core.logging import get_logger

log = get_logger("ai.model")

MIN_SAMPLES = 200        # below this any fit is noise — stay in data-collection
RETRAIN_EVERY = 25       # new closed trades between refits
_KEEP = 5                # model versions kept on disk


def _models_dir() -> str:
    d = config.env("BL_MODELS_DIR",
                   os.path.join(os.path.dirname(config.env(
                       "DB_PATH", os.path.join(os.getcwd(), "data", "journal.db"))),
                       "models"))
    os.makedirs(d, exist_ok=True)
    return d


def _metrics_path() -> str:
    return os.path.join(_models_dir(), "metrics.json")


def _load_metrics() -> dict:
    try:
        with open(_metrics_path()) as f:
            return json.load(f)
    except Exception:
        return {}


def _prune() -> None:
    """Keep only the newest _KEEP model artifacts on disk."""
    d = _models_dir()
    pkls = sorted((f for f in os.listdir(d)
                   if f.startswith("model_v") and f.endswith(".pkl")),
                  key=lambda f: int(f[7:-4]))
    for old in pkls[:-_KEEP]:
        try:
            os.remove(os.path.join(d, old))
        except OSError:
            pass


def _vectorize(dataset: list[tuple[dict, str, float]]):
    """(X, y, feature_names) — one stable, sorted feature order forever."""
    names = sorted({k for feats, _, _ in dataset for k in feats})
    X = np.array([[float(feats.get(k, 0.0) or 0.0) for k in names]
                  for feats, _, _ in dataset])
    y = np.array([1 if r > 0 else 0 for _, _, r in dataset])
    return X, y, names


class ProbabilityModel:
    """Loads the latest ACCEPTED artifact; predicts calibrated P(win)."""

    def __init__(self) -> None:
        self._model = None
        self._calib = None
        self._names: list[str] = []
        self._loaded_version = -1

    def _refresh(self) -> None:
        meta = _load_metrics()
        version = int(meta.get("accepted_version", -1))
        if version < 0 or version == self._loaded_version:
            return
        path = os.path.join(_models_dir(), f"model_v{version}.pkl")
        try:
            with open(path, "rb") as f:
                bundle = pickle.load(f)
            self._model, self._calib = bundle["model"], bundle["calibrator"]
            self._names = bundle["feature_names"]
            self._loaded_version = version
            log.info("ModelLoaded", version=version)
        except Exception as exc:
            log.warning("ModelLoadFailed", version=version, error=str(exc))

    def predict(self, features: dict) -> float | None:
        """Calibrated P(win) for one signal's feature snapshot, or None while no
        accepted model exists (data-collection phase)."""
        self._refresh()
        if self._model is None:
            return None
        x = np.array([[float(features.get(k, 0.0) or 0.0) for k in self._names]])
        raw = float(self._model.predict_proba(x)[0, 1])
        p = float(self._calib.predict([raw])[0]) if self._calib is not None else raw
        return min(1.0, max(0.0, p))


def train(dataset: list[tuple[dict, str, float]]) -> dict | None:
    """Fit + calibrate + validate on a chronological split; PROMOTE only if the
    validation Brier beats the base-rate baseline. Returns the metrics dict of
    the accepted model, or None when rejected/insufficient."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import brier_score_loss

    if len(dataset) < MIN_SAMPLES:
        return None
    X, y, names = _vectorize(dataset)
    # 3-way CHRONOLOGICAL split: fit on train, fit the isotonic calibrator on
    # calib, score Brier on the UNTOUCHED test tail — scoring on the same slice
    # the calibrator saw would flatter every model, including pure noise.
    c1, c2 = int(len(y) * 0.6), int(len(y) * 0.8)
    if c1 < 50 or len(set(y[:c1])) < 2 or len(set(y[c1:c2])) < 2 \
            or len(set(y[c2:])) < 2:
        return None                                   # degenerate split

    model = HistGradientBoostingClassifier(random_state=42, max_depth=4,
                                           max_iter=200, learning_rate=0.08)
    model.fit(X[:c1], y[:c1])
    calib = IsotonicRegression(out_of_bounds="clip").fit(
        model.predict_proba(X[c1:c2])[:, 1], y[c1:c2])
    p_test = np.clip(calib.predict(model.predict_proba(X[c2:])[:, 1]), 0.0, 1.0)

    base = float(y[:c2].mean())                       # base-rate baseline
    brier = float(brier_score_loss(y[c2:], p_test))
    brier_base = float(brier_score_loss(y[c2:], np.full(len(y) - c2, base)))

    meta = _load_metrics()
    version = int(meta.get("last_version", -1)) + 1
    metrics = {"version": version, "trained_at": int(time.time()),
               "n": len(y), "n_train": c1, "brier": round(brier, 4),
               "brier_base": round(brier_base, 4), "base_rate": round(base, 3),
               # require a real margin over the base rate — a lucky 0.5% "win"
               # on a 20% test tail is noise, not skill
               "accepted": brier < brier_base * 0.98}
    prev_brier = meta.get("accepted_brier")

    meta["last_version"] = version
    meta["last_trained_n"] = len(y)
    meta.setdefault("history", []).append(metrics)
    meta["history"] = meta["history"][-20:]

    # promote only when better than baseline AND not clearly worse than the
    # currently accepted model (auto-rollback = never promoting a regression)
    if metrics["accepted"] and (prev_brier is None or brier <= prev_brier * 1.10):
        with open(os.path.join(_models_dir(), f"model_v{version}.pkl"), "wb") as f:
            pickle.dump({"model": model, "calibrator": calib,
                         "feature_names": names}, f)
        meta["accepted_version"] = version
        meta["accepted_brier"] = brier
        log.info("ModelPromoted", **{k: v for k, v in metrics.items()
                                     if k != "accepted"})
        _prune()
    else:
        log.info("ModelRejected", version=version, brier=brier,
                 brier_base=brier_base, prev_brier=prev_brier)

    with open(_metrics_path(), "w") as f:
        json.dump(meta, f, indent=1)
    return metrics if metrics["accepted"] else None


def maybe_retrain(journal) -> None:
    """Cheap idempotent hook for the scan loop: refit once RETRAIN_EVERY new
    closed labelled trades have accumulated (sub-second on <10k rows)."""
    try:
        dataset = journal.features_dataset()
        if len(dataset) < MIN_SAMPLES:
            return
        meta = _load_metrics()
        if len(dataset) - int(meta.get("last_trained_n", 0)) < RETRAIN_EVERY \
                and meta.get("last_trained_n"):
            return
        train(dataset)
    except Exception as exc:                           # never break the scan loop
        log.warning("RetrainFailed", error=str(exc))

"""Feature Engineering Engine (SRS doc 09).

Transforms a normalized market window + the analytical-engine outputs into a flat
numerical feature vector, captured at signal time and stored with each signal.
When the AI/Probability engines (docs 16-17) train later, they learn from these
features against the recorded TP/SL outcomes.

Every feature is deterministic, NaN-safe and bounded — no lookahead, no business
logic (doc 09 §1, §23). Values are normalized (ATR units, ratios, 0–1 flags) so a
tree/GBM model can consume them directly regardless of instrument price scale.
"""
from __future__ import annotations

import math

import pandas as pd

from ..core.logging import get_logger

log = get_logger("features")

_TREND_CODE = {
    "Strong Bearish": -3, "Bearish": -2, "Weak Bearish": -1, "Sideways": 0,
    "Weak Bullish": 1, "Bullish": 2, "Strong Bullish": 3,
}
_PD_CODE = {"Discount": -1, "Equilibrium": 0, "Premium": 1}
_AMD_CODE = {"": 0, "Accumulation": 1, "Manipulation": 2, "Distribution": 3}


def _safe(x: float, default: float = 0.0) -> float:
    return default if x is None or math.isnan(x) or math.isinf(x) else float(x)


class FeatureEngineer:
    def extract(self, symbol: str, df: pd.DataFrame, *, structure, liquidity,
                order_block, fvg, ict, direction: str, ts=None) -> dict[str, float]:
        f: dict[str, float] = {}
        f.update(self._price(df))
        f.update(self._trend(df, structure))
        f.update(self._momentum(df))
        f.update(self._volatility(df))
        f.update(self._volume(df))
        f.update(self._structure(structure))
        f.update(self._liquidity(df, liquidity))
        f.update(self._zone(df, order_block, fvg, direction))
        f.update(self._ict(ict))
        f.update(self._statistical(df))
        f.update(self._time(ts))
        f["direction_long"] = 1.0 if direction == "BUY" else 0.0
        return {k: round(_safe(v), 6) for k, v in f.items()}

    # ── price geometry (in ATR units / ratios) ────────────────────────────
    def _price(self, df: pd.DataFrame) -> dict:
        c = df["close"].iloc[-1]
        o = df["open"].iloc[-1]
        hi = df["high"].iloc[-1]
        lo = df["low"].iloc[-1]
        atr = self._atr(df)
        rng = (hi - lo) or 1e-9
        ema20 = df["ema20"].iloc[-1]
        ema50 = df["ema50"].iloc[-1]
        ema200 = df["ema200"].iloc[-1]
        return {
            "close_vs_ema20_atr": (c - ema20) / atr,
            "close_vs_ema50_atr": (c - ema50) / atr,
            "close_vs_ema200_atr": (c - ema200) / atr,
            "ema20_vs_ema50_atr": (ema20 - ema50) / atr,
            "ema50_vs_ema200_atr": (ema50 - ema200) / atr,
            "body_pct": abs(c - o) / rng,
            "upper_wick_pct": (hi - max(o, c)) / rng,
            "lower_wick_pct": (min(o, c) - lo) / rng,
            "close_pos_in_range": (c - lo) / rng,
            "range_atr": rng / atr,
        }

    def _trend(self, df: pd.DataFrame, structure) -> dict:
        ema20 = df["ema20"]
        ema50 = df["ema50"]
        atr = self._atr(df)
        slope20 = (ema20.iloc[-1] - ema20.iloc[-6]) / atr if len(df) > 6 else 0.0
        slope50 = (ema50.iloc[-1] - ema50.iloc[-6]) / atr if len(df) > 6 else 0.0
        labels = [s.get("label", "") for s in structure.swings]
        return {
            "ema20_slope_atr": slope20,
            "ema50_slope_atr": slope50,
            "trend_code": _TREND_CODE.get(structure.trend.value, 0),
            "hh_count": labels.count("HH"),
            "hl_count": labels.count("HL"),
            "lh_count": labels.count("LH"),
            "ll_count": labels.count("LL"),
        }

    def _momentum(self, df: pd.DataFrame) -> dict:
        rsi = df["rsi"]
        rsi_now = rsi.iloc[-1]
        rsi_prev = rsi.iloc[-4] if len(df) > 4 else rsi_now
        closes = df["close"]
        up = down = 0
        for i in range(len(df) - 1, max(0, len(df) - 8), -1):
            if closes.iloc[i] > closes.iloc[i - 1]:
                up += 1
                if down:
                    break
            elif closes.iloc[i] < closes.iloc[i - 1]:
                down += 1
                if up:
                    break
        return {
            "rsi": rsi_now,
            "rsi_slope": rsi_now - rsi_prev,
            "consec_up": up,
            "consec_down": down,
        }

    def _volatility(self, df: pd.DataFrame) -> dict:
        atr = self._atr(df)
        c = df["close"].iloc[-1]
        atr_avg = df["atr"].tail(50).mean() if "atr" in df else atr
        rets = df["close"].pct_change().tail(20)
        return {
            "atr_pct": atr / c if c else 0.0,
            "atr_vs_avg": atr / atr_avg if atr_avg else 1.0,
            "realized_vol_20": float(rets.std()) if len(rets) > 2 else 0.0,
        }

    def _volume(self, df: pd.DataFrame) -> dict:
        vol = df["volume"].iloc[-1]
        avg = df["vol_avg20"].iloc[-1] if "vol_avg20" in df else vol
        return {
            "rel_volume": vol / avg if avg else 1.0,
            "volume_trend": (vol - df["volume"].tail(10).mean()) / (avg or 1.0),
        }

    def _structure(self, structure) -> dict:
        return {
            "structure_strength": structure.strength,
            "bos": 1.0 if structure.bos else 0.0,
            "choch": 1.0 if structure.choch else 0.0,
            "break_bullish": 1.0 if "bullish" in (structure.bos_direction,
                                                  structure.choch_direction) else 0.0,
        }

    def _liquidity(self, df: pd.DataFrame, liq) -> dict:
        return {
            "liquidity_score": liq.liquidity_score,
            "liquidity_swept": 1.0 if liq.liquidity_swept else 0.0,
            "stop_hunt": 1.0 if liq.stop_hunt else 0.0,
            "dist_to_pool_atr": liq.distance if liq.distance is not None else 5.0,
            "bsl_present": 1.0 if liq.buy_side_liquidity else 0.0,
            "ssl_present": 1.0 if liq.sell_side_liquidity else 0.0,
        }

    def _zone(self, df: pd.DataFrame, ob, fvg, direction: str) -> dict:
        c = df["close"].iloc[-1]
        atr = self._atr(df)
        best_ob = ob.best
        near_fvg = fvg.nearest
        ob_ok = best_ob is not None
        fvg_ok = near_fvg is not None
        ob_dist = abs(((best_ob.price_low + best_ob.price_high) / 2 - c) / atr) if ob_ok else 5.0
        fvg_dist = abs((near_fvg.midpoint - c) / atr) if fvg_ok else 5.0
        return {
            "ob_present": 1.0 if ob_ok else 0.0,
            "ob_score": best_ob.score if ob_ok else 0.0,
            "ob_fresh": 1.0 if (ob_ok and best_ob.fresh) else 0.0,
            "ob_dist_atr": ob_dist,
            "fvg_present": 1.0 if fvg_ok else 0.0,
            "fvg_score": near_fvg.score if fvg_ok else 0.0,
            "fvg_fill_pct": near_fvg.filled_pct if fvg_ok else 0.0,
            "fvg_dist_atr": fvg_dist,
        }

    def _ict(self, ict) -> dict:
        return {
            "ict_score": ict.ict_score,
            "premium_discount": _PD_CODE.get(ict.premium_discount, 0),
            "ote": 1.0 if ict.ote else 0.0,
            "kill_zone": 1.0 if ict.kill_zone else 0.0,
            "judas_swing": 1.0 if ict.judas_swing else 0.0,
            "amd_phase": _AMD_CODE.get(ict.amd_phase, 0),
            "smt_divergence": 1.0 if ict.smt_divergence else 0.0,
        }

    def _statistical(self, df: pd.DataFrame) -> dict:
        window = df["close"].tail(50)
        c = df["close"].iloc[-1]
        mean = window.mean()
        std = window.std() or 1e-9
        rank = float((window < c).sum()) / len(window) if len(window) else 0.5
        rets = df["close"].pct_change().tail(50).dropna()
        return {
            "zscore_50": (c - mean) / std,
            "percentile_50": rank,
            "ret_skew_50": float(rets.skew()) if len(rets) > 3 else 0.0,
            "ret_kurt_50": float(rets.kurt()) if len(rets) > 3 else 0.0,
        }

    def _time(self, ts) -> dict:
        if ts is None:
            return {"hour": 0.0, "day_of_week": 0.0}
        return {"hour": float(ts.hour), "day_of_week": float(ts.weekday())}

    @staticmethod
    def _atr(df: pd.DataFrame) -> float:
        atr = float(df["atr"].iloc[-1]) if "atr" in df else 0.0
        return atr if atr > 0 else float((df["high"] - df["low"]).tail(14).mean()) or 1e-9

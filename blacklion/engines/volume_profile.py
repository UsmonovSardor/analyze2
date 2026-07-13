"""Institutional Volume Profile engine (TITAN Bible ch.7/33).

Deterministic VWAP / POC / Value Area / Volume-Spike / Absorption / Exhaustion
over the analysis frame. HONEST DATA NOTE: MT5 forex delivers TICK volume only —
there is no true buy/sell Delta or Cumulative Delta, so the bible's Delta factors
(7.10–7.11) are deliberately OMITTED rather than faked. Everything here is
computable from OHLC + (tick) volume.

Bias: price above VWAP + expanding volume → bullish; below → bearish. The Rule
Engine folds vp_score into confluence and adds valued reasons; it never trades on
volume alone.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel

from ..core.logging import get_logger

log = get_logger("engines.volume_profile")


class VolumeProfileResult(BaseModel):
    symbol: str
    vwap: float = 0.0
    price_vs_vwap: str = "at"          # above | below | at
    poc: float = 0.0                   # price with the most traded volume
    vah: float = 0.0                   # value-area high (70% of volume)
    val: float = 0.0                   # value-area low
    in_value_area: bool = False
    volume_spike: bool = False
    spike_ratio: float = 0.0           # current vs average volume
    absorption: bool = False           # big volume, tiny range → reversal risk
    exhaustion: bool = False           # price extends, volume fades → trend weak
    bias: str = "neutral"              # bullish | bearish | neutral
    vp_score: int = 0                  # 0–100


class VolumeProfileEngine:
    def __init__(self, bins: int = 24, spike_mult: float = 2.0,
                 value_area_pct: float = 0.70) -> None:
        self.bins = bins
        self.spike_mult = spike_mult
        self.value_area_pct = value_area_pct

    def analyze(self, symbol: str, df: pd.DataFrame) -> VolumeProfileResult:
        if not {"high", "low", "close", "volume"} <= set(df.columns) or len(df) < 20:
            return VolumeProfileResult(symbol=symbol)

        high = df["high"].to_numpy(float)
        low = df["low"].to_numpy(float)
        close = df["close"].to_numpy(float)
        vol = df["volume"].to_numpy(float)
        typical = (high + low + close) / 3.0
        last = float(close[-1])

        # ── VWAP (7.12) — volume-weighted average over the frame ───────────
        vsum = float(vol.sum()) or 1.0
        vwap = float((typical * vol).sum() / vsum)
        rng = float(high.max() - low.min()) or 1e-9
        tol = rng * 0.001
        pvv = "above" if last > vwap + tol else "below" if last < vwap - tol else "at"

        # ── Volume Profile histogram → POC + Value Area (7.13–7.14) ────────
        lo_p, hi_p = float(low.min()), float(high.max())
        edges = np.linspace(lo_p, hi_p, self.bins + 1)
        hist = np.zeros(self.bins)
        idx = np.clip(np.digitize(typical, edges) - 1, 0, self.bins - 1)
        for i, v in zip(idx, vol):
            hist[i] += v
        centers = (edges[:-1] + edges[1:]) / 2.0
        poc = float(centers[int(hist.argmax())])

        # value area: grow out from POC until 70% of volume is covered
        order = sorted(range(self.bins), key=lambda i: hist[i], reverse=True)
        target = hist.sum() * self.value_area_pct
        covered, chosen = 0.0, []
        for i in order:
            covered += hist[i]
            chosen.append(i)
            if covered >= target:
                break
        vah = float(centers[max(chosen)])
        val = float(centers[min(chosen)])
        in_va = val <= last <= vah

        # ── Volume behaviour (7.5 / 7.8 / 7.9) ─────────────────────────────
        avg_vol = float(vol[-21:-1].mean()) if len(vol) >= 21 else float(vol[:-1].mean() or 1.0)
        cur_vol = float(vol[-1])
        spike_ratio = cur_vol / avg_vol if avg_vol > 0 else 0.0
        spike = spike_ratio >= self.spike_mult

        bar_rng = float(high[-1] - low[-1])
        avg_rng = float((high[-21:-1] - low[-21:-1]).mean()) if len(df) >= 21 else bar_rng
        # absorption: heavy volume but the bar barely moved (institutions soaking)
        absorption = spike and avg_rng > 0 and bar_rng < 0.6 * avg_rng
        # exhaustion: price made a new extreme on FADING volume (trend tiring)
        new_extreme = (last >= float(high[-6:-1].max())
                       or last <= float(low[-6:-1].min()))
        exhaustion = new_extreme and spike_ratio < 0.8

        bias = "bullish" if pvv == "above" else "bearish" if pvv == "below" else "neutral"

        # ── vp_score (adapted 7.15, Delta factors dropped) ─────────────────
        score = 0
        score += 30 if spike else 0
        score += 25 if pvv != "at" else 0                # clear VWAP side
        score += 20 if in_va else 10                     # inside value area = fair
        score += 15 if not exhaustion else 0
        score += 10 if not absorption else 0
        vp_score = max(0, min(100, score))

        return VolumeProfileResult(
            symbol=symbol, vwap=round(vwap, 6), price_vs_vwap=pvv,
            poc=round(poc, 6), vah=round(vah, 6), val=round(val, 6),
            in_value_area=in_va, volume_spike=spike,
            spike_ratio=round(spike_ratio, 2), absorption=absorption,
            exhaustion=exhaustion, bias=bias, vp_score=vp_score)

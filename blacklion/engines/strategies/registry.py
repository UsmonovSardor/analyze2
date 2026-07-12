"""Detector registry — runs every enabled detector and returns matches best-first.

New detectors (ICT Turtle Soup, Unicorn, AMD… — phase 2) register here; the Rule
Engine never imports a concrete detector.
"""
from __future__ import annotations

from ...core import config
from .base import DetectorContext, StrategyMatch
from .ict_models import AMDPowerOfThree, TurtleSoup, Unicorn
from .setup_a import TrendPullback
from .setup_b import RangeBreakout

DETECTORS = [TrendPullback(), RangeBreakout(),
             TurtleSoup(), Unicorn(), AMDPowerOfThree()]

# strategies.yaml section name per detector code
_SECTION = {"A": "trend_pullback", "B": "range_breakout",
            "TSOUP": "turtle_soup", "UNICORN": "unicorn", "AMD": "amd_po3"}


def _cfg() -> dict:
    try:
        return config.load("strategies")
    except Exception:
        return {}


def detect_all(ctx: DetectorContext) -> list[StrategyMatch]:
    """Every enabled detector's match for this context, sorted by score desc.
    A detector exception must never kill the scan — it is logged upstream by the
    Rule Engine; here we simply skip it."""
    cfg = _cfg()
    out: list[StrategyMatch] = []
    for det in DETECTORS:
        section = dict(cfg.get(_SECTION.get(det.code, ""), {}))
        if not section.get("enabled", True):
            continue
        ctx.cfg = section
        try:
            match = det.detect(ctx)
        except Exception:
            continue                                   # defensive: one bad detector ≠ no scan
        if match is not None:
            out.append(match)
    return sorted(out, key=lambda m: m.score, reverse=True)

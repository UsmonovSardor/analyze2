"""Multi-Timeframe cascade + Conflict Engine (TITAN Bible ch.6/21).

The bible's law: no signal on one timeframe alone. Trend must agree DOWN the
cascade D1 → H4 → H1 → M15. This module reads the trend on every timeframe
ABOVE the entry TF and reports alignment, so the Rule Engine can:
  • hard-reject a setup that CONFLICTS with a higher timeframe (6.9, 6.11)
  • feed the alignment ratio into confidence (6.10 Multi-Timeframe Score)

Data-light: one MarketStructure pass per higher TF, cached inside a scan.
"""
from __future__ import annotations

from pydantic import BaseModel

from ..core.logging import get_logger
from .market_structure import MarketStructureEngine

log = get_logger("engines.mtf")

# full hierarchy, highest → lowest (bible 6.2)
_CASCADE = ["MN", "W1", "D1", "H4", "H1", "M30", "M15", "M5", "M1"]


class MTFResult(BaseModel):
    trends: dict[str, str] = {}      # tf → "BUY" / "SELL" / "NO TRADE"
    bullish: int = 0
    bearish: int = 0
    total: int = 0

    def agrees(self, direction: str) -> int:
        """How many higher timeframes agree with the trade direction."""
        want = "BUY" if direction == "BUY" else "SELL"
        return sum(1 for t in self.trends.values() if t == want)

    def opposing(self, direction: str) -> int:
        """How many higher timeframes point the OTHER way."""
        against = "SELL" if direction == "BUY" else "BUY"
        return sum(1 for t in self.trends.values() if t == against)

    def conflicts(self, direction: str, min_opposing: int = 2) -> bool:
        """Reject only when at least `min_opposing` higher timeframes oppose the
        trade — one lone disagreeing TF (common on a fresh session when D1/H4/H1
        are still transitioning) is tolerated; a majority against is not
        (softened bible 6.9/6.11)."""
        return self.opposing(direction) >= min_opposing

    def score(self, direction: str) -> float:
        """0..1 alignment ratio for the confidence engine."""
        return self.agrees(direction) / self.total if self.total else 0.5


class MultiTimeframe:
    """Reads higher-timeframe trends for a symbol/entry-TF."""

    def __init__(self, structure: MarketStructureEngine | None = None,
                 candles: int = 200) -> None:
        self.structure = structure or MarketStructureEngine()
        self.candles = candles

    def higher_tfs(self, entry_tf: str) -> list[str]:
        """Every timeframe strictly above the entry TF, up to Daily."""
        if entry_tf not in _CASCADE:
            return []
        idx = _CASCADE.index(entry_tf)
        # the bible's context cascade is D1 → H4 → H1 (the TFs that define trend);
        # M30/M15 are entry TFs, not higher context.
        return [tf for tf in _CASCADE[:idx] if tf in ("D1", "H4", "H1")]

    def analyze(self, source, symbol: str, entry_tf: str) -> MTFResult:
        res = MTFResult()
        for tf in self.higher_tfs(entry_tf):
            try:
                df = source.fetch(symbol, tf, self.candles)
                trend = self.structure.analyze(symbol, df).trend
            except Exception as exc:                   # a missing TF must not kill the scan
                log.warning("MTFFetchFailed", symbol=symbol, tf=tf, error=str(exc))
                continue
            label = "BUY" if trend.bullish else "SELL" if trend.bearish else "NO TRADE"
            res.trends[tf] = label
            res.total += 1
            if label == "BUY":
                res.bullish += 1
            elif label == "SELL":
                res.bearish += 1
        return res

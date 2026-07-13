"""Signal pipeline (SRS doc 30 §3 end-to-end workflow, `signal_builder` folder).

Wires the analytical engines together for one symbol/timeframe:

    Structure → Liquidity → Order Block → FVG → ICT → Rule Engine

Each engine stays independent and separately testable; this module only
orchestrates the call order and shares intermediate results. The AI Decision +
Probability engines (docs 16–17) plug in after the Rule Engine once trained.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from ..core.logging import get_logger
from .fvg import FVGEngine
from .ict import ICTEngine
from .liquidity import LiquidityEngine
from .manipulation import ManipulationEngine
from .market_structure import MarketStructureEngine
from .order_block import OrderBlockEngine
from .rule_engine import RuleDecision, RuleEngine
from .volume_profile import VolumeProfileEngine

log = get_logger("engines.pipeline")


class SignalPipeline:
    def __init__(self) -> None:
        self.structure = MarketStructureEngine()
        self.liquidity = LiquidityEngine()
        self.order_block = OrderBlockEngine()
        self.fvg = FVGEngine()
        self.ict = ICTEngine()
        self.volume = VolumeProfileEngine()          # TITAN Bible ch.7
        self.manipulation = ManipulationEngine()     # TITAN Bible ch.8
        self.rules = RuleEngine()
        self.last: dict = {}         # last run's engine outputs (for feature capture)

    def run(self, symbol: str, df: pd.DataFrame,
            htf_bullish: bool | None = None,
            ts: datetime | None = None, mtf=None) -> RuleDecision:
        """df must carry open/high/low/close/volume/atr; newest row last.
        `mtf` (MTFResult) carries the higher-timeframe cascade for the conflict
        engine + confidence (TITAN Bible ch.6)."""
        structure = self.structure.analyze(symbol, df)
        swings = self.structure.classify(self.structure.detect_swings(df))
        liquidity = self.liquidity.analyze(symbol, df, swings)
        order_block = self.order_block.analyze(symbol, df)
        fvg = self.fvg.analyze(symbol, df)
        ict = self.ict.analyze(symbol, df, swings,
                               trend_bullish=structure.trend.bullish, ts=ts)
        volume = self.volume.analyze(symbol, df)
        manipulation = self.manipulation.analyze(symbol, df, liquidity=liquidity)
        decision = self.rules.evaluate(symbol, df, structure, liquidity,
                                       order_block, fvg, ict,
                                       htf_bullish=htf_bullish, mtf=mtf,
                                       volume=volume, manipulation=manipulation)
        # stash the engine outputs so the Feature Engineer can snapshot them for
        # the signal that was just produced (single-threaded runtime)
        self.last = {"structure": structure, "liquidity": liquidity,
                     "order_block": order_block, "fvg": fvg, "ict": ict,
                     "volume": volume, "manipulation": manipulation}
        log.info("PipelineComplete", symbol=symbol, decision=decision.decision,
                 confluence=decision.confluence_score)
        return decision

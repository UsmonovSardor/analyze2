"""Named-strategy detector contract.

Deterministic port of the strategy catalog (docs/strategies/strategy.md, from the
"analyze" bot's LLM skill) — every named setup becomes a testable Python detector
instead of prompt text. SRS "no black box": each detector is pure, reads only the
engine outputs + indicator columns it is given, and explains itself with valued
reasons.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

import pandas as pd
from pydantic import BaseModel

from ..fvg import FVGResult
from ..ict import ICTResult
from ..liquidity import LiquidityResult
from ..market_structure import StructureResult
from ..order_block import OrderBlockResult

Regime = Literal["strong_bull", "bull_pullback", "range", "chop",
                 "bear_rally", "strong_bear"]


@dataclass
class DetectorContext:
    """Everything a detector may read — one bundle so adding an input never
    changes every detector's signature."""
    symbol: str
    df: pd.DataFrame                 # entry TF with atr/rsi/ema columns
    structure: StructureResult
    liquidity: LiquidityResult
    order_block: OrderBlockResult
    fvg: FVGResult
    ict: ICTResult
    htf_bullish: bool | None
    regime: Regime
    cfg: dict = field(default_factory=dict)   # this detector's strategies.yaml section


class StrategyMatch(BaseModel):
    name: str                        # display name, e.g. "Trend Pullback"
    code: str                        # short code, e.g. "A"
    direction: Literal["BUY", "SELL"]
    score: int                       # 0–10 confluence scorecard total
    scorecard: dict[str, int] = {}   # per-factor points (trend/level/volume/…)
    reasons: list[str] = []          # valued, Uzbek — appended to the signal


class StrategyDetector(Protocol):
    code: str
    name: str

    def detect(self, ctx: DetectorContext) -> StrategyMatch | None: ...

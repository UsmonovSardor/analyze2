"""Execution Engine (SRS doc 19).

Safely executes ALREADY-APPROVED signals. It never generates decisions — it only
executes trades cleared by Rule → Probability → Risk. Handles pre-execution
validation, slippage guard, order submission with retry, and position sync.

Broker-agnostic: depends only on the Broker Protocol, so the same code runs the
paper broker in tests and the MT5 bridge in production.
"""
from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel

from ..core import config
from ..core.events import bus
from ..core.logging import get_logger
from ..engines.rule_engine import Signal
from ..risk import RiskDecision
from .broker import Broker, OrderRequest, OrderResult

log = get_logger("execution")


class ExecutionResult(BaseModel):
    status: Literal["EXECUTED", "REJECTED", "FAILED"]
    ticket: str = ""
    fill_price: float = 0.0
    volume: float = 0.0
    slippage: float = 0.0
    latency_ms: int = 0
    reason: str = ""


class ExecutionEngine:
    def __init__(self, broker: Broker, *, max_retries: int = 3,
                 max_slippage_points: dict[str, float] | None = None) -> None:
        self.broker = broker
        self.max_retries = max_retries
        # per-symbol slippage cap in price points (doc 19 §8)
        self.max_slippage = max_slippage_points or {}
        self._symbols = config.load("symbols")["symbols"]

    def execute(self, signal: Signal, risk: RiskDecision) -> ExecutionResult:
        # Execution requires prior approval from Rule + Risk (doc 19 §1).
        if not risk.approved or risk.lot_size <= 0:
            return ExecutionResult(status="REJECTED", reason="risk not approved")

        # ── Pre-execution validation (doc 19 §7) ──────────────────────────
        ok, why = self._pre_validate(signal)
        if not ok:
            bus.publish("ExecutionRejected", symbol=signal.symbol, reason=why)
            return ExecutionResult(status="REJECTED", reason=why)

        req = OrderRequest(
            symbol=signal.symbol, direction=signal.direction,
            volume=risk.lot_size, entry=0.0,           # market order
            stop_loss=signal.stop_loss, take_profit=signal.tp2,
            comment=f"BL conf={signal.confidence}")

        # ── Submit with retry + slippage guard (doc 19 §13) ───────────────
        result = self._submit_with_retry(req)
        if not result.ok:
            bus.publish("ExecutionFailed", symbol=signal.symbol, error=result.error)
            return ExecutionResult(status="FAILED", reason=result.error)

        cap = self.max_slippage.get(signal.symbol)
        if cap is not None and result.slippage > cap:
            # filled worse than allowed → unwind immediately
            self.broker.close(result.ticket)
            bus.publish("ExecutionFailed", symbol=signal.symbol, error="slippage exceeded")
            return ExecutionResult(status="FAILED", reason="slippage exceeded")

        bus.publish("OrderExecuted", symbol=signal.symbol, ticket=result.ticket)
        log.info("OrderExecuted", symbol=signal.symbol, ticket=result.ticket,
                 fill=result.fill_price, lots=result.volume)
        return ExecutionResult(status="EXECUTED", ticket=result.ticket,
                               fill_price=result.fill_price, volume=result.volume,
                               slippage=result.slippage, latency_ms=result.latency_ms)

    # ── validation ────────────────────────────────────────────────────────
    def _pre_validate(self, signal: Signal) -> tuple[bool, str]:
        if not self.broker.is_connected():
            return False, "broker not connected"
        if not self.broker.market_open(signal.symbol):
            return False, "market closed"
        max_spread = self._symbols.get(signal.symbol, {}).get("max_spread_points", 0)
        if max_spread:
            spread = self.broker.spread_points(signal.symbol)
            if spread > max_spread:
                return False, f"spread {spread} > {max_spread}"
        return True, "ok"

    def _submit_with_retry(self, req: OrderRequest) -> OrderResult:
        last = OrderResult(ok=False, error="not attempted")
        for attempt in range(1, self.max_retries + 1):
            last = self.broker.place_order(req)
            if last.ok:
                return last
            log.warning("OrderRetry", symbol=req.symbol, attempt=attempt, error=last.error)
            time.sleep(min(0.5 * attempt, 2.0))       # exponential-ish backoff
        return last

    # ── Position management (doc 19 §10–12) ───────────────────────────────
    def move_to_breakeven(self, ticket: str, entry: float) -> bool:
        """Trail the stop to entry — mirrors the journal's post-TP1 breakeven so
        broker and journal never disagree (old-bot lesson in docs/ROADMAP.md)."""
        return self.broker.modify(ticket, stop_loss=entry)

    def partial_close(self, ticket: str, fraction: float) -> OrderResult:
        for p in self.broker.positions():
            if p.ticket == ticket:
                return self.broker.close(ticket, volume=round(p.volume * fraction, 2))
        return OrderResult(ok=False, error="unknown ticket")

    def sync(self) -> list[str]:
        """Return broker tickets currently open (position reconciliation, doc 19 §9)."""
        return [p.ticket for p in self.broker.positions()]

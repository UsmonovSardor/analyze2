"""Risk Management Engine (SRS doc 18).

No trade may be executed unless approved here. The model/rules propose; this
engine disposes. Responsibilities: position sizing, SL/TP/RR validation, daily &
weekly loss locks, exposure and correlation caps, portfolio heat.

Pure and deterministic — given the same signal + account state it always returns
the same decision, so it is fully unit-testable (SRS doc 18 §21).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..core import config
from ..core.events import bus
from ..core.logging import get_logger
from ..engines.rule_engine import Signal

log = get_logger("risk")


class OpenPosition(BaseModel):
    symbol: str
    direction: Literal["BUY", "SELL"]
    risk_pct: float                  # open risk as % of balance (to the stop)


class AccountState(BaseModel):
    balance: float
    equity: float
    open_positions: list[OpenPosition] = []
    realized_pnl_today_pct: float = 0.0     # negative = loss, as % of balance
    realized_pnl_week_pct: float = 0.0
    contract_size: float = 1.0              # units per 1.0 lot (100000 for FX)


class RiskDecision(BaseModel):
    approved: bool
    reasons: list[str] = []
    lot_size: float = 0.0
    risk_pct: float = 0.0
    rr: float = 0.0
    risk_grade: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "LOW"


class RiskEngine:
    def __init__(self) -> None:
        r = config.load("risk")
        self.risk_pct: float = float(r["risk_per_trade_pct"])
        self.max_risk_pct: float = float(r["max_risk_per_trade_pct"])
        self.min_rr: float = float(r["minimum_rr"])
        self.daily_limit: float = float(r["daily_loss_limit_pct"])
        self.weekly_limit: float = float(r["weekly_loss_limit_pct"])
        self.max_open: int = int(r["maximum_open_trades"])
        self.max_heat: float = float(r["maximum_portfolio_heat_pct"])
        self.max_exposure: dict = r.get("max_exposure_pct", {})
        self.corr_groups: list[list[str]] = r.get("correlation_groups", [])
        self._symbols = config.load("symbols")["symbols"]

    def evaluate(self, signal: Signal, account: AccountState) -> RiskDecision:
        reasons: list[str] = []

        # ── Loss locks (doc 18 §11–12) ────────────────────────────────────
        if account.realized_pnl_today_pct <= -self.daily_limit:
            reasons.append(f"daily loss limit {self.daily_limit}% reached")
        if account.realized_pnl_week_pct <= -self.weekly_limit:
            reasons.append(f"weekly loss limit {self.weekly_limit}% reached")

        # ── Open-trade & heat caps (doc 18 §13, §15) ──────────────────────
        if len(account.open_positions) >= self.max_open:
            reasons.append(f"max open trades ({self.max_open}) reached")
        current_heat = sum(p.risk_pct for p in account.open_positions)
        if current_heat + self.risk_pct > self.max_heat:
            reasons.append(f"portfolio heat would exceed {self.max_heat}%")

        # ── Exposure by market (doc 18 §13) ───────────────────────────────
        market = self._symbols.get(signal.symbol, {}).get("market", "forex")
        cap = self.max_exposure.get(market)
        if cap is not None:
            same_market = sum(
                p.risk_pct for p in account.open_positions
                if self._symbols.get(p.symbol, {}).get("market") == market)
            if same_market + self.risk_pct > cap:
                reasons.append(f"{market} exposure would exceed {cap}%")

        # ── Correlation filter (doc 18 §14) ───────────────────────────────
        if self._correlated_conflict(signal, account):
            reasons.append("correlated same-direction exposure already open")

        # ── SL/TP/RR validation (doc 18 §8–10) ────────────────────────────
        r = abs(signal.entry - signal.stop_loss)
        if r <= 0:
            reasons.append("stop distance is zero")
        rr = abs(signal.tp2 - signal.entry) / r if r > 0 else 0.0
        if rr < self.min_rr:
            reasons.append(f"RR {rr:.2f} below minimum {self.min_rr}")

        if reasons:
            bus.publish("TradeRejected", symbol=signal.symbol, reasons=reasons)
            return RiskDecision(approved=False, reasons=reasons, rr=round(rr, 2))

        lot = self._position_size(signal, account, r)
        grade = self._risk_grade(current_heat + self.risk_pct)
        bus.publish("TradeApproved", symbol=signal.symbol, lot=lot)
        return RiskDecision(approved=True, lot_size=lot, risk_pct=self.risk_pct,
                            rr=round(rr, 2), risk_grade=grade)

    def _correlated_conflict(self, signal: Signal, account: AccountState) -> bool:
        groups = [g for g in self.corr_groups if signal.symbol in g]
        if not groups:
            return False
        peers = {s for g in groups for s in g if s != signal.symbol}
        return any(p.symbol in peers and p.direction == signal.direction
                   for p in account.open_positions)

    def _position_size(self, signal: Signal, account: AccountState, stop_dist: float) -> float:
        """Lot size so a full stop-out loses ~risk_pct of balance (doc 18 §6)."""
        risk_money = account.balance * self.risk_pct / 100
        loss_per_lot = stop_dist * account.contract_size
        if loss_per_lot <= 0:
            return 0.0
        return round(risk_money / loss_per_lot, 2)

    def _risk_grade(self, projected_heat: float) -> Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
        ratio = projected_heat / self.max_heat if self.max_heat else 1.0
        if ratio >= 1.0:
            return "CRITICAL"
        if ratio >= 0.75:
            return "HIGH"
        if ratio >= 0.5:
            return "MEDIUM"
        return "LOW"

"""Paper (simulated) broker — deterministic, in-memory.

Implements the Broker Protocol so the Execution Engine can be tested and dry-run
without any live credentials (SRS doc 29 §3 — development uses mock brokers).
The same Execution Engine code later drives the real MT5 adapter unchanged.
"""
from __future__ import annotations

import itertools

from .broker import BrokerPosition, OrderRequest, OrderResult


class PaperBroker:
    def __init__(self, prices: dict[str, float] | None = None,
                 spread_points: dict[str, float] | None = None,
                 fill_slippage: float = 0.0) -> None:
        self._prices = dict(prices or {})
        self._spreads = dict(spread_points or {})
        self._slip = fill_slippage
        self._positions: dict[str, BrokerPosition] = {}
        self._ids = itertools.count(1)
        self._connected = False
        self._closed_only = False        # simulate market closed

    # ── test/control helpers ──────────────────────────────────────────────
    def set_price(self, symbol: str, price: float) -> None:
        self._prices[symbol] = price

    def set_market_closed(self, closed: bool) -> None:
        self._closed_only = closed

    # ── Broker Protocol ───────────────────────────────────────────────────
    def connect(self) -> bool:
        self._connected = True
        return True

    def is_connected(self) -> bool:
        return self._connected

    def market_open(self, symbol: str) -> bool:
        return not self._closed_only

    def current_price(self, symbol: str) -> float:
        return self._prices.get(symbol, 0.0)

    def spread_points(self, symbol: str) -> float:
        return self._spreads.get(symbol, 0.0)

    def place_order(self, req: OrderRequest) -> OrderResult:
        if not self._connected:
            return OrderResult(ok=False, error="not connected")
        price = req.entry or self.current_price(req.symbol)
        if price <= 0:
            return OrderResult(ok=False, error="no price")
        fill = price + (self._slip if req.direction == "BUY" else -self._slip)
        ticket = str(next(self._ids))
        self._positions[ticket] = BrokerPosition(
            ticket=ticket, symbol=req.symbol, direction=req.direction,
            volume=req.volume, entry=fill, stop_loss=req.stop_loss,
            take_profit=req.take_profit)
        return OrderResult(ok=True, ticket=ticket, fill_price=fill,
                           volume=req.volume, slippage=abs(fill - price), latency_ms=1)

    def modify(self, ticket: str, *, stop_loss: float | None = None,
               take_profit: float | None = None) -> bool:
        pos = self._positions.get(ticket)
        if not pos:
            return False
        self._positions[ticket] = pos.model_copy(update={
            "stop_loss": stop_loss if stop_loss is not None else pos.stop_loss,
            "take_profit": take_profit if take_profit is not None else pos.take_profit,
        })
        return True

    def close(self, ticket: str, volume: float | None = None) -> OrderResult:
        pos = self._positions.get(ticket)
        if not pos:
            return OrderResult(ok=False, error="unknown ticket")
        price = self.current_price(pos.symbol) or pos.entry
        vol = pos.volume if volume is None else min(volume, pos.volume)
        if vol >= pos.volume:
            del self._positions[ticket]
        else:
            self._positions[ticket] = pos.model_copy(update={"volume": pos.volume - vol})
        return OrderResult(ok=True, ticket=ticket, fill_price=price, volume=vol, latency_ms=1)

    def positions(self) -> list[BrokerPosition]:
        return list(self._positions.values())

"""Broker adapter contract (SRS doc 19 §15 — "architecture must allow additional
adapters"; doc 30 §5 — "new adapters can be added without changing business logic").

Every broker (MT5, Binance, Bybit, paper) implements this one Protocol, so the
Execution Engine never imports a concrete broker. This is the seam the SRS's
modular design requires — swap the adapter, keep the logic.
"""
from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel


class OrderRequest(BaseModel):
    symbol: str
    direction: Literal["BUY", "SELL"]
    volume: float                    # lots
    entry: float                     # 0 ⇒ market order
    stop_loss: float
    take_profit: float               # single broker-side TP (usually tp2)
    comment: str = ""


class OrderResult(BaseModel):
    ok: bool
    ticket: str = ""
    fill_price: float = 0.0
    volume: float = 0.0
    slippage: float = 0.0
    latency_ms: int = 0
    error: str = ""
    retcode: int = 0                 # raw broker return code (MT5 TRADE_RETCODE_*); 0 ⇒ n/a


class BrokerPosition(BaseModel):
    ticket: str
    symbol: str
    direction: Literal["BUY", "SELL"]
    volume: float
    entry: float
    stop_loss: float
    take_profit: float
    profit: float = 0.0


@runtime_checkable
class Broker(Protocol):
    """Minimal surface the Execution Engine depends on."""

    def connect(self) -> bool: ...

    def is_connected(self) -> bool: ...

    def market_open(self, symbol: str) -> bool: ...

    def current_price(self, symbol: str) -> float: ...

    def spread_points(self, symbol: str) -> float: ...

    def contract_size(self, symbol: str) -> float: ...

    def place_order(self, req: OrderRequest) -> OrderResult: ...

    def modify(self, ticket: str, *, stop_loss: float | None = None,
               take_profit: float | None = None) -> bool: ...

    def close(self, ticket: str, volume: float | None = None) -> OrderResult: ...

    def positions(self) -> list[BrokerPosition]: ...

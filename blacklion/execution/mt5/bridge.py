"""MetaTrader 5 broker adapter (SRS doc 19 §15).

The MT5 Python package (`MetaTrader5`) is Windows-only. On the Hetzner Linux
server the terminal runs under Wine inside the `mt5` container (gmag11 image),
which exposes an rpyc classic server on MT5_BRIDGE_PORT; this adapter connects
through the `mt5linux` client, which proxies every call/constant to the remote
`MetaTrader5` module and returns results by value (numpy arrays survive intact).
On a native Windows host, set BL_MT5_NATIVE=1 to import `MetaTrader5` directly.

Both paths satisfy the same Broker Protocol as PaperBroker, so the Execution
Engine is identical in test and production. Requires broker credentials
(MT5_LOGIN / MT5_PASSWORD / MT5_SERVER) — see .env.example.

This adapter is intentionally not unit-tested here (it needs a live terminal);
its logic is exercised by the integration/demo run once a broker is configured.
"""
from __future__ import annotations

import os
import time

from ...core.logging import get_logger
from ..broker import BrokerPosition, OrderRequest, OrderResult

log = get_logger("execution.mt5")

# MT5 order-type / return constants (avoid importing the package until connect()).
_DEVIATION = 20          # max price deviation in points for market orders


class MT5Broker:
    def __init__(self) -> None:
        self._native = os.getenv("BL_MT5_NATIVE") == "1"
        self._host = os.getenv("MT5_BRIDGE_HOST", "mt5")
        self._port = int(os.getenv("MT5_BRIDGE_PORT", "8001"))
        self._login = os.getenv("MT5_LOGIN", "")
        self._password = os.getenv("MT5_PASSWORD", "")
        self._server = os.getenv("MT5_SERVER", "")
        self._mt5 = None            # the MetaTrader5 module (native or mt5linux proxy)

    # ── connection ────────────────────────────────────────────────────────
    def connect(self) -> bool:
        try:
            self._mt5 = self._import_mt5()
        except Exception as exc:                       # pragma: no cover - env dependent
            log.error("MT5ImportFailed", error=str(exc))
            return False
        kwargs: dict = {}
        if self._login and self._password and self._server:
            kwargs = {"login": int(self._login), "password": self._password,
                      "server": self._server}
        if not self._mt5.initialize(**kwargs):         # pragma: no cover
            log.error("MT5InitFailed", error=str(self._mt5.last_error()))
            return False
        log.info("MT5Connected", server=self._server, native=self._native)
        return True

    def _import_mt5(self):
        if self._native:                               # pragma: no cover - Windows only
            import MetaTrader5 as mt5
            return mt5
        from mt5linux import MetaTrader5              # pragma: no cover - needs bridge
        return MetaTrader5(host=self._host, port=self._port)

    def is_connected(self) -> bool:                    # pragma: no cover
        return self._mt5 is not None and bool(self._mt5.terminal_info())

    # ── market data ───────────────────────────────────────────────────────
    def market_open(self, symbol: str) -> bool:        # pragma: no cover
        info = self._mt5.symbol_info(symbol)
        return bool(info and info.trade_mode != 0)

    def current_price(self, symbol: str) -> float:     # pragma: no cover
        tick = self._mt5.symbol_info_tick(symbol)
        return float(tick.ask) if tick else 0.0

    def spread_points(self, symbol: str) -> float:     # pragma: no cover
        info = self._mt5.symbol_info(symbol)
        return float(info.spread) if info else 0.0

    # ── orders ────────────────────────────────────────────────────────────
    def place_order(self, req: OrderRequest) -> OrderResult:   # pragma: no cover
        mt5 = self._mt5
        tick = mt5.symbol_info_tick(req.symbol)
        if not tick:
            return OrderResult(ok=False, error="no tick")
        is_buy = req.direction == "BUY"
        price = tick.ask if is_buy else tick.bid
        order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": req.symbol,
            "volume": float(req.volume),
            "type": order_type,
            "price": price,
            "sl": req.stop_loss,
            "tp": req.take_profit,
            "deviation": _DEVIATION,
            "comment": req.comment or "BLACK LION",
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        t0 = time.time()
        res = mt5.order_send(request)
        latency = int((time.time() - t0) * 1000)
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            return OrderResult(ok=False, latency_ms=latency,
                               error=f"retcode {getattr(res, 'retcode', '?')}")
        return OrderResult(ok=True, ticket=str(res.order), fill_price=float(res.price),
                           volume=float(res.volume), slippage=abs(res.price - price),
                           latency_ms=latency)

    def modify(self, ticket: str, *, stop_loss=None, take_profit=None) -> bool:  # pragma: no cover
        mt5 = self._mt5
        pos = self._find(ticket)
        if not pos:
            return False
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": int(ticket),
            "symbol": pos.symbol,
            "sl": stop_loss if stop_loss is not None else pos.stop_loss,
            "tp": take_profit if take_profit is not None else pos.take_profit,
        }
        res = mt5.order_send(request)
        return bool(res and res.retcode == mt5.TRADE_RETCODE_DONE)

    def close(self, ticket: str, volume=None) -> OrderResult:   # pragma: no cover
        mt5 = self._mt5
        pos = self._find(ticket)
        if not pos:
            return OrderResult(ok=False, error="unknown ticket")
        tick = mt5.symbol_info_tick(pos.symbol)
        is_buy = pos.direction == "BUY"
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": float(volume or pos.volume),
            "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
            "position": int(ticket),
            "price": tick.bid if is_buy else tick.ask,
            "deviation": _DEVIATION,
        }
        res = mt5.order_send(request)
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            return OrderResult(ok=False, error=f"retcode {getattr(res, 'retcode', '?')}")
        return OrderResult(ok=True, ticket=ticket, fill_price=float(res.price),
                           volume=float(res.volume))

    def account_info(self) -> tuple[float, float]:     # pragma: no cover
        """Real (balance, equity) from the terminal — the risk engine's account
        view in trade modes, replacing the journal's shadow book."""
        info = self._mt5.account_info()
        if info is None:
            return 0.0, 0.0
        return float(info.balance), float(info.equity)

    def positions(self) -> list[BrokerPosition]:       # pragma: no cover
        out: list[BrokerPosition] = []
        for p in self._mt5.positions_get() or []:
            out.append(BrokerPosition(
                ticket=str(p.ticket), symbol=p.symbol,
                direction="BUY" if p.type == self._mt5.ORDER_TYPE_BUY else "SELL",
                volume=float(p.volume), entry=float(p.price_open),
                stop_loss=float(p.sl), take_profit=float(p.tp), profit=float(p.profit)))
        return out

    def _find(self, ticket: str) -> BrokerPosition | None:     # pragma: no cover
        return next((p for p in self.positions() if p.ticket == ticket), None)

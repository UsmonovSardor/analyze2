"""BLACK LION AI entrypoint.

Selects a broker + market-data source from the environment, then runs the scan
loop (Runtime): source → pipeline → risk → execution → journal → outcomes.

Data feed and execution are decoupled — the safe default sends signals only:

  - BL_MT5_DATA=1     → MT5 candle source (real broker data via the Wine bridge)
  - BL_MT5_EXECUTE=1  → MT5 broker places demo/live orders (edge unproven → demo)
  - neither / default → YahooSource + PaperBroker (pure dry-run, no credentials)

With BL_MT5_DATA=1 alone, the bot analyses real MT5 candles but routes through
PaperBroker: it journals + Telegrams signals and places NO orders. Every signal
is journalled regardless, so history accumulates for the AI engines that train
later. If the MT5 bridge is unreachable, we fall back to Yahoo + PaperBroker
rather than crash.
"""
from __future__ import annotations

import os

from .core import config
from .core.logging import get_logger
from .execution import PaperBroker
from .journal import Journal
from .runtime import Runtime

log = get_logger("main")


def _paper_stack():
    from .data.sources import YahooSource
    broker = PaperBroker()
    broker.connect()
    return broker, YahooSource(), "paper"


def build_stack():
    """Return (broker, source, kind) chosen from the environment.

      - BL_MANUAL_TRADE=1 → live MT5 broker, but the scanner never auto-trades;
        orders open only when the user taps the Telegram "Avto-savdo" button.
      - BL_MT5_EXECUTE=1  → live MT5 broker AND the scanner auto-trades signals.
    """
    want_data = os.getenv("BL_MT5_DATA") == "1"
    want_exec = os.getenv("BL_MT5_EXECUTE") == "1"
    want_manual = os.getenv("BL_MANUAL_TRADE") == "1"
    if not (want_data or want_exec or want_manual):
        return _paper_stack()

    from .data.sources import MT5Source, YahooSource
    from .execution.mt5 import MT5Broker
    mt5 = MT5Broker()
    if not mt5.connect():
        log.error("MT5Unavailable", note="bridge down — falling back to Yahoo + Paper")
        return _paper_stack()

    # MT5 candles when asked; keep the connected handle even in data-only mode.
    source = MT5Source(getattr(mt5, "_mt5", None)) if want_data else YahooSource()
    if want_exec:
        return mt5, source, "mt5-live"          # scanner auto-trades through MT5
    if want_manual:
        return mt5, source, "mt5-manual"        # live broker, button-only trades
    broker = PaperBroker()
    broker.connect()
    return broker, source, "mt5-data"           # real feed, signals only, no orders


def main() -> None:
    env = config.env("BL_ENV", "development")
    broker, source, kind = build_stack()

    runtime = Runtime(source, broker, journal=Journal())
    # Scanner auto-trades only in full-auto mode; the button trades in either
    # trade mode. Data/paper modes show no button and place no orders.
    runtime.auto_execute = kind == "mt5-live"
    runtime.notifier.trade_enabled = kind in ("mt5-manual", "mt5-live")
    log.info("Boot", env=env, broker=kind, connected=broker.is_connected(),
             symbols=len(runtime.symbols),
             version=__import__("blacklion").__version__)
    if kind == "paper":
        log.info("DryRun", note="PaperBroker + Yahoo feed — signals journalled, "
                 "no live orders")
    elif kind == "mt5-data":
        log.info("SignalsOnly", note="MT5 feed + PaperBroker — real candles, "
                 "signals to Telegram, NO orders (edge unproven)")
    elif kind == "mt5-manual":
        log.warning("ManualTrade", note="MT5 demo — signals only; orders open ONLY "
                    "when the user taps Avto-savdo (edge unproven)")
    elif kind == "mt5-live":
        log.warning("LiveExecution", note="MT5 broker placing orders — ensure this "
                    "is a DEMO account (edge unproven)")

    scan = int(config.env("BL_SCAN_INTERVAL", "1800"))
    outcome = int(config.env("BL_OUTCOME_INTERVAL", "300"))
    try:
        runtime.run_forever(scan_interval=scan, outcome_interval=outcome)
    except KeyboardInterrupt:
        log.info("Shutdown")


if __name__ == "__main__":
    main()

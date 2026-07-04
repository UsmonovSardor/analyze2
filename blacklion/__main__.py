"""BLACK LION AI entrypoint.

Selects a broker + market-data source from the environment, then runs the scan
loop (Runtime): source → pipeline → risk → execution → journal → outcomes.

  - MT5_LOGIN set  → MT5 bridge broker + MT5 candle source (live/demo terminal)
  - otherwise      → PaperBroker + YahooSource (safe dry-run, no credentials);
                     every signal is still journalled so history accumulates for
                     the AI/Probability engines that train later.
"""
from __future__ import annotations

import os

from .core import config
from .core.logging import get_logger
from .execution import PaperBroker
from .journal import Journal
from .runtime import Runtime

log = get_logger("main")


def build_stack():
    """Return (broker, source, kind) chosen from the environment."""
    if os.getenv("MT5_LOGIN"):
        from .data.sources import MT5Source
        from .execution.mt5 import MT5Broker
        broker = MT5Broker()
        broker.connect()
        # the source shares the broker's connected MT5 handle
        return broker, MT5Source(getattr(broker, "_mt5", None)), "mt5"
    from .data.sources import YahooSource
    broker = PaperBroker()
    broker.connect()
    return broker, YahooSource(), "paper"


def main() -> None:
    env = config.env("BL_ENV", "development")
    broker, source, kind = build_stack()

    runtime = Runtime(source, broker, journal=Journal())
    log.info("Boot", env=env, broker=kind, connected=broker.is_connected(),
             symbols=len(runtime.symbols),
             version=__import__("blacklion").__version__)
    if kind == "paper":
        log.info("DryRun", note="no MT5 credentials — PaperBroker + Yahoo feed, "
                 "signals journalled, no live orders")

    scan = int(config.env("BL_SCAN_INTERVAL", "1800"))
    outcome = int(config.env("BL_OUTCOME_INTERVAL", "300"))
    try:
        runtime.run_forever(scan_interval=scan, outcome_interval=outcome)
    except KeyboardInterrupt:
        log.info("Shutdown")


if __name__ == "__main__":
    main()

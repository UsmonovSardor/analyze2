"""BLACK LION AI entrypoint.

Boots the runtime and selects a broker adapter from the environment:
  - MT5_LOGIN set        → MT5 bridge (live/demo terminal)
  - otherwise            → PaperBroker (safe dry-run, no credentials)

The full scan loop (market-data feed → pipeline → risk → execution) is wired in
Phase 7+ as data sources come online. For now this validates configuration and
broker connectivity so the container has a real, non-crashing boot path.
"""
from __future__ import annotations

import os

from .core import config
from .core.logging import get_logger
from .engines.pipeline import SignalPipeline
from .execution import ExecutionEngine, PaperBroker
from .risk import RiskEngine

log = get_logger("main")


def build_broker():
    if os.getenv("MT5_LOGIN"):
        from .execution.mt5 import MT5Broker
        return MT5Broker(), "mt5"
    return PaperBroker(), "paper"


def main() -> None:
    env = config.env("BL_ENV", "development")
    broker, kind = build_broker()
    connected = broker.connect()

    # instantiate the core engines so config errors surface at boot
    pipeline = SignalPipeline()      # noqa: F841 — wired into scan loop next phase
    risk = RiskEngine()              # noqa: F841
    execution = ExecutionEngine(broker)  # noqa: F841

    symbols = list(config.load("symbols")["symbols"])
    log.info("Boot", env=env, broker=kind, connected=connected,
             symbols=len(symbols), version=__import__("blacklion").__version__)

    if kind == "paper":
        log.info("DryRun", note="no MT5 credentials — paper broker, no live orders")

    # Placeholder until the market-data feed lands (Phase 2 wiring): keep the
    # process alive so docker `restart: unless-stopped` doesn't thrash.
    try:
        import time
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        log.info("Shutdown")


if __name__ == "__main__":
    main()

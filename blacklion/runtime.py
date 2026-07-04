"""Runtime scan loop — ties the whole pipeline together (SRS doc 30 §3).

    source → SignalPipeline → Journal → RiskEngine → ExecutionEngine → Journal

One scan_once() is deterministic given a ReplaySource + PaperBroker, so the whole
trading flow is unit-testable end to end. check_outcomes() walks open trades and
closes them on SL/TP — mirroring the broker so journal and broker never disagree
(carry-over lesson from the old bot).
"""
from __future__ import annotations

import time

from .core import config
from .core.logging import get_logger
from .data.sources import MarketDataSource
from .engines.market_structure import MarketStructureEngine
from .engines.pipeline import SignalPipeline
from .execution import Broker, ExecutionEngine
from .journal import Journal
from .risk import AccountState, OpenPosition, RiskEngine
from .telegram import Notifier

log = get_logger("runtime")


class Runtime:
    def __init__(self, source: MarketDataSource, broker: Broker,
                 journal: Journal | None = None,
                 notifier: Notifier | None = None) -> None:
        self.source = source
        self.broker = broker
        self.journal = journal or Journal()
        self.notifier = notifier or Notifier()
        self.pipeline = SignalPipeline()
        self.structure = MarketStructureEngine()
        self.risk = RiskEngine()
        self.execution = ExecutionEngine(broker)
        self.symbols: list[str] = list(config.load("symbols")["symbols"])
        self.entry_tf: str = config.engine("market_structure").get("entry_tf", "H1")
        self.context_tf: str = config.engine("market_structure").get("context_tf", "H4")
        self.candles: int = 300
        self.balance: float = float(config.env("BL_BALANCE", "10000"))
        self.cooldown_hours: int = int(config.env("BL_COOLDOWN_HOURS", "3"))

    # ── one scan across the watchlist ─────────────────────────────────────
    def scan_once(self) -> list[int]:
        """Returns the signal ids generated this pass (recorded, maybe executed)."""
        produced: list[int] = []
        for symbol in self.symbols:
            try:
                sid = self._scan_symbol(symbol)
                if sid is not None:
                    produced.append(sid)
            except Exception as exc:                     # never let one symbol halt the scan
                log.error("ScanError", symbol=symbol, error=str(exc))
        return produced

    def _scan_symbol(self, symbol: str) -> int | None:
        if self.journal.recent_signal_for(symbol, self.cooldown_hours):
            return None
        df = self.source.fetch(symbol, self.entry_tf, self.candles)
        htf = self.source.fetch(symbol, self.context_tf, self.candles)
        htf_bullish = self.structure.analyze(symbol, htf).trend.bullish
        decision = self.pipeline.run(symbol, df, htf_bullish=htf_bullish)
        if decision.signal is None:
            return None

        sig = decision.signal
        sid = self.journal.record_signal(sig)          # record EVERY signal (for AI later)
        self.notifier.on_signal(sig, sid, market_ctx=f"{symbol} · {self.entry_tf}")

        account = self._account_state()
        risk = self.risk.evaluate(sig, account)
        if not risk.approved:
            log.info("RiskRejected", symbol=symbol, reasons=risk.reasons)
            return sid

        result = self.execution.execute(sig, risk)
        if result.status == "EXECUTED":
            self.journal.record_execution(sid, result.ticket, result.volume,
                                          result.fill_price)
            log.info("SignalExecuted", symbol=symbol, id=sid, ticket=result.ticket)
        else:
            log.info("ExecutionSkipped", symbol=symbol, status=result.status,
                     reason=result.reason)
        return sid

    # ── outcome tracking for open trades ──────────────────────────────────
    def check_outcomes(self) -> None:
        for row in self.journal.open_trades():
            try:
                price = self.broker.current_price(row.symbol)
                if price <= 0:
                    continue
                self._resolve(row, price)
            except Exception as exc:
                log.error("OutcomeError", id=row.id, error=str(exc))

    def _resolve(self, row, price: float) -> None:
        long = row.direction == "BUY"
        r = abs(row.entry - row.stop_loss) or 1e-9
        hit_sl = (price <= row.stop_loss) if long else (price >= row.stop_loss)
        hit_tp3 = (price >= row.tp3) if long else (price <= row.tp3)
        if hit_sl:
            result_r = -1.0 if row.status == "open" else 0.0   # breakeven after TP1
            status = "stopped" if row.status == "open" else "breakeven"
            self.journal.close_signal(row.id, status, result_r)
            if row.ticket:
                self.broker.close(row.ticket)
            self.notifier.on_outcome(row, status, result_r)
        elif hit_tp3:
            result_r = round(abs(row.tp3 - row.entry) / r, 2)
            self.journal.close_signal(row.id, "tp3", result_r)
            if row.ticket:
                self.broker.close(row.ticket)
            self.notifier.on_outcome(row, "tp3", result_r)

    def _account_state(self) -> AccountState:
        positions = []
        for row in self.journal.open_trades():
            positions.append(OpenPosition(
                symbol=row.symbol, direction=row.direction, risk_pct=self.risk.risk_pct))
        return AccountState(
            balance=self.balance, equity=self.balance,
            open_positions=positions,
            realized_pnl_today_pct=self.journal.realized_r(86400) * self.risk.risk_pct,
            realized_pnl_week_pct=self.journal.realized_r(7 * 86400) * self.risk.risk_pct,
            contract_size=100000.0)

    # ── blocking loop for __main__ ────────────────────────────────────────
    def run_forever(self, scan_interval: int = 1800, outcome_interval: int = 300) -> None:  # pragma: no cover
        from datetime import datetime, timezone
        last_scan = last_outcome = 0.0
        last_digest_day = None
        digest_hour = int(config.env("BL_DIGEST_HOUR_UTC", "16"))
        while True:
            now = time.time()
            if now - last_scan >= scan_interval:
                last_scan = now
                found = self.scan_once()
                log.info("ScanDone", signals=len(found))
            if now - last_outcome >= outcome_interval:
                last_outcome = now
                self.check_outcomes()
            # allowlisted Telegram commands (/stats, /open, ...)
            if self.notifier.enabled:
                self.notifier.poll_commands(self.journal)
            # once-a-day digest
            utc = datetime.now(timezone.utc)
            if utc.hour >= digest_hour and last_digest_day != utc.date():
                last_digest_day = utc.date()
                if self.notifier.enabled:
                    self.notifier.send_daily_digest(self.journal)
            time.sleep(5)

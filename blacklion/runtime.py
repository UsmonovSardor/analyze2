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
from .features import FeatureEngineer
from .execution import Broker, ExecutionEngine
from .journal import Journal
from .monitoring import HealthMonitor, HealthReport
from .risk import AccountState, OpenPosition, RiskEngine
from .telegram import Notifier

log = get_logger("runtime")

# Position management: scale out 40% at TP1, 40% at TP2, 20% runner to TP3, and
# ride the stop to breakeven once TP1 prints. Same weights as backtest.engine so
# live and backtest agree on a trade's R (doc 04/21). Must sum to 1.0.
_SCALE = (0.4, 0.4, 0.2)


class Runtime:
    def __init__(self, source: MarketDataSource, broker: Broker,
                 journal: Journal | None = None,
                 notifier: Notifier | None = None) -> None:
        self.source = source
        self.broker = broker
        self.journal = journal or Journal()
        self.notifier = notifier or Notifier()
        self.monitor = HealthMonitor()
        self.notifier.health_provider = self.health   # /health command support
        self.pipeline = SignalPipeline()
        self.features = FeatureEngineer()
        self.structure = MarketStructureEngine()
        self.risk = RiskEngine()
        self.execution = ExecutionEngine(broker)
        self.symbols: list[str] = list(config.load("symbols")["symbols"])
        # Multi-timeframe scan: each (entry, context) pair is scanned per symbol,
        # so M15 setups (frequent) accumulate history far faster than H1 alone.
        self.scan_tfs: list[tuple[str, str]] = self._parse_tfs(
            config.env("BL_SCAN_TIMEFRAMES", "M15:H1,H1:H4"))
        self.candles: int = 300
        self.balance: float = float(config.env("BL_BALANCE", "10000"))
        self.cooldown_hours: int = int(config.env("BL_COOLDOWN_HOURS", "3"))

    @staticmethod
    def _parse_tfs(spec: str) -> list[tuple[str, str]]:
        pairs = []
        for part in spec.split(","):
            if ":" in part:
                e, c = part.strip().split(":")
                pairs.append((e.strip(), c.strip()))
        return pairs or [("H1", "H4")]

    @property
    def entry_tf(self) -> str:                     # primary TF (outcome-check default)
        return self.scan_tfs[0][0]

    # ── one scan across the watchlist × timeframes ────────────────────────
    def scan_once(self) -> list[int]:
        """Returns the signal ids generated this pass (recorded, maybe executed)."""
        produced: list[int] = []
        errors = fetched = 0
        for symbol in self.symbols:
            for entry_tf, context_tf in self.scan_tfs:
                try:
                    sid = self._scan_symbol(symbol, entry_tf, context_tf)
                    fetched += 1
                    if sid is not None:
                        produced.append(sid)
                except Exception as exc:             # never let one symbol/TF halt the scan
                    errors += 1
                    log.error("ScanError", symbol=symbol, tf=entry_tf, error=str(exc))
        # feed is healthy if at least one symbol/TF returned data this pass
        self.monitor.record_scan(signals=len(produced), errors=errors,
                                 feed_ok=fetched > 0)
        return produced

    def health(self) -> HealthReport:
        return self.monitor.snapshot(
            signals_today=self.journal.signals_today(),
            open_trades=len(self.journal.open_trades()),
            scan_interval=int(config.env("BL_SCAN_INTERVAL", "1800")))

    def _scan_symbol(self, symbol: str, entry_tf: str, context_tf: str) -> int | None:
        # per-(symbol,TF) cooldown so M15 and H1 don't block each other
        if self.journal.recent_signal_for(symbol, self.cooldown_hours, timeframe=entry_tf):
            return None
        df = self.source.fetch(symbol, entry_tf, self.candles)
        htf = self.source.fetch(symbol, context_tf, self.candles)
        htf_bullish = self.structure.analyze(symbol, htf).trend.bullish
        decision = self.pipeline.run(symbol, df, htf_bullish=htf_bullish)
        if decision.signal is None:
            return None

        sig = decision.signal
        sid = self.journal.record_signal(sig, timeframe=entry_tf)   # record EVERY signal
        # snapshot the feature vector at signal time → labelled training data (doc 09)
        try:
            feats = self.features.extract(symbol, df, direction=sig.direction,
                                          **self.pipeline.last)
            self.journal.record_features(sid, feats)
        except Exception as exc:
            log.error("FeatureError", symbol=symbol, error=str(exc))
        self.notifier.on_signal(sig, sid, df=df, timeframe=entry_tf,
                                market_ctx=f"{symbol} · {entry_tf}")

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
        # Price of record is the DATA SOURCE (Yahoo/MT5), not the broker — in
        # dry-run the PaperBroker has no quotes. Fetch each symbol's latest bar
        # once per cycle and use its high/low so intrabar TP/SL hits are caught.
        cache: dict[tuple[str, str], tuple[float, float]] = {}
        for row in self.journal.open_trades():
            try:
                key = (row.symbol, row.timeframe)      # track on the trade's own TF
                if key not in cache:
                    df = self.source.fetch(row.symbol, row.timeframe, 3)
                    cache[key] = (float(df["high"].iloc[-1]),
                                  float(df["low"].iloc[-1]))
                hi, lo = cache[key]
                self._resolve(row, hi, lo)
            except Exception as exc:
                # A symbol that left the watchlist (e.g. crypto after the switch
                # to the MT5 feed, which has none) can never be priced again —
                # expire it once instead of erroring every cycle forever.
                if row.symbol not in self.symbols:
                    self.journal.close_signal(row.id, "expired", 0.0)
                    log.info("OutcomeExpired", id=row.id, symbol=row.symbol,
                             reason="symbol no longer in watchlist")
                else:
                    log.error("OutcomeError", id=row.id, error=str(exc))

    def _resolve(self, row, hi: float, lo: float) -> None:
        """Advance a trade at most one stage per bar, mirroring backtest.engine so
        live outcomes and backtests share one definition of R. Scale out 40% at
        TP1 and 40% at TP2; once TP1 prints the stop rides at breakeven (entry)
        for the runner, so a reversal after TP1 books a partial win, not −1R."""
        long = row.direction == "BUY"
        sign = 1.0 if long else -1.0
        e = row.entry
        r = abs(e - row.stop_loss) or 1e-9
        w1, w2, w3 = _SCALE
        reached = (lambda lvl: hi >= lvl) if long else (lambda lvl: lo <= lvl)
        # after TP1 the stop trails up to breakeven (entry) and stays there
        eff_sl = e if row.status in ("tp1", "tp2") else row.stop_loss
        stop_hit = (lo <= eff_sl) if long else (hi >= eff_sl)

        if stop_hit:
            if row.status == "open":
                self._close(row, "stopped", -1.0)
                return
            booked = w1 * sign * (row.tp1 - e) / r
            if row.status == "tp2":
                booked += w2 * sign * (row.tp2 - e) / r
            rem = {"tp1": w2 + w3, "tp2": w3}[row.status]   # runner still live
            booked += rem * sign * (eff_sl - e) / r          # = 0 at breakeven
            self._close(row, "breakeven", round(booked, 2))
        elif reached(row.tp3) and row.status == "tp2":
            total = sign * (w1 * (row.tp1 - e) + w2 * (row.tp2 - e)
                            + w3 * (row.tp3 - e)) / r
            self._close(row, "tp3", round(total, 2))
        elif reached(row.tp2) and row.status == "tp1":
            booked = sign * (w1 * (row.tp1 - e) + w2 * (row.tp2 - e)) / r
            self._advance(row, "tp2", round(booked, 2))
        elif reached(row.tp1) and row.status == "open":
            self._advance(row, "tp1", round(w1 * sign * (row.tp1 - e) / r, 2))

    def _close(self, row, status: str, result_r: float) -> None:
        self.journal.close_signal(row.id, status, result_r)
        if row.ticket:
            self.broker.close(row.ticket)
        self.notifier.on_outcome(row, status, result_r)

    def _advance(self, row, status: str, booked_r: float) -> None:
        """Book a partial scale-out and keep the runner live. Signals-only today:
        the scale-out and breakeven are recorded in the journal for honest R;
        real partial broker exits (execution.partial_close / move_to_breakeven)
        are wired when BL_MT5_EXECUTE lands and the edge is proven."""
        self.journal.advance(row.id, status, booked_r)
        self.notifier.on_outcome(row, status, booked_r)

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
        digest_hour = int(config.env("BL_DIGEST_HOUR_UTC", "16"))
        # If the bot (re)starts AFTER the digest hour, treat today's digest as
        # already sent — otherwise every redeploy re-sends the daily summary.
        _boot = datetime.now(timezone.utc)
        last_digest_day = _boot.date() if _boot.hour >= digest_hour else None
        while True:
            now = time.time()
            if now - last_scan >= scan_interval:
                last_scan = now
                found = self.scan_once()
                log.info("ScanDone", signals=len(found))
                # health check + rate-limited alert on trouble (doc 24)
                report = self.health()
                if report.status != "HEALTHY":
                    log.warning("HealthDegraded", status=report.status,
                                errors=report.consecutive_errors, feed=report.feed_ok)
                if self.notifier.enabled and self.monitor.should_alert(report):
                    self.notifier.send_health_alert(report)
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

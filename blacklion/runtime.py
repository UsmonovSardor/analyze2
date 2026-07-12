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
from .execution.engine import MARKET_CLOSED
from .journal import Journal
from .monitoring import HealthMonitor, HealthReport
from .risk import AccountState, OpenPosition, RiskEngine
from .telegram import Notifier

log = get_logger("runtime")

# Position management: scale out 40% at TP1, 40% at TP2, 20% runner to TP3, and
# ride the stop to breakeven once TP1 prints. Same weights as backtest.engine so
# live and backtest agree on a trade's R (doc 04/21). Must sum to 1.0.
_SCALE = (0.4, 0.4, 0.2)

# entry-TF bar length in minutes — for the time-stop's bars-open estimate
_TF_MIN = {"M1": 1, "M5": 5, "M15": 15, "M30": 30,
           "H1": 60, "H4": 240, "D1": 1440}


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
        symbol_cfg = config.load("symbols")["symbols"]
        self.symbols: list[str] = list(symbol_cfg)
        # units per 1.0 lot per symbol (XAUUSD=100 vs FX=100000) — sizing with the
        # wrong contract rounds the lot to 0.00 and vetoes every metal trade. The
        # live broker value (symbol_info.trade_contract_size) overrides config.
        self._contracts: dict[str, float] = {
            sym: float(cfg.get("contract", 100000.0))
            for sym, cfg in symbol_cfg.items()}
        # Multi-timeframe scan: each (entry, context) pair is scanned per symbol,
        # so M15 setups (frequent) accumulate history far faster than H1 alone.
        self.scan_tfs: list[tuple[str, str]] = self._parse_tfs(
            config.env("BL_SCAN_TIMEFRAMES", "M15:H1,H1:H4"))
        self.candles: int = 300
        self.balance: float = float(config.env("BL_BALANCE", "10000"))
        self.cooldown_hours: int = int(config.env("BL_COOLDOWN_HOURS", "3"))
        # When False the scanner never places orders on its own — trades are opened
        # only when the user taps the "Avto-savdo" button (manual mode). main() sets
        # this per broker mode; default True preserves auto/paper-execute behaviour.
        self.auto_execute: bool = config.env("BL_AUTO_EXECUTE", "1") == "1"
        # Publish tier: signals below this confidence stay journal-only (shadow
        # candidates that still label the ML dataset) — the group sees only 80+.
        self.min_publish: int = int(config.engine("rule_engine")
                                    .get("minimum_publish_confidence", 80))
        # smart trade management knobs (risk.yaml) — early exits + runner trail
        self.mgmt: dict = config.load("risk").get("trade_management", {})
        self.notifier.trade_executor = self.execute_signal   # Telegram button hook

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
        # Publish tier — sub-threshold signals are recorded (labelled ML data,
        # cooldown applies) but never published or traded: the group only ever
        # sees top-tier signals and never a button on a weak setup.
        if sig.confidence < self.min_publish:
            log.info("SignalShadowed", id=sid, symbol=symbol, tf=entry_tf,
                     confidence=sig.confidence, min_publish=self.min_publish)
            return sid

        self.notifier.on_signal(sig, sid, df=df, timeframe=entry_tf,
                                market_ctx=f"{symbol} · {entry_tf}")

        # Manual mode: the scanner only signals; the order is opened later when the
        # user taps the button (execute_signal). Auto mode keeps the old behaviour.
        if not self.auto_execute:
            return sid

        account = self._account_state(symbol)
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

    def execute_signal(self, sid: int) -> str:
        """Open the trade for a journalled signal on demand (Telegram button). The
        order carries SL + a TP3 backstop; check_outcomes then manages the 40/40/20
        scale-out and breakeven on the live position. Returns a status line."""
        row = self.journal.get(sid)
        if row is None:
            return f"⚠️ Signal #{sid} topilmadi."
        if row.ticket:
            return f"ℹ️ #{sid} {row.symbol} allaqachon ochilgan (ticket {row.ticket})."
        if row.status != "open":
            return f"⚠️ #{sid} endi ochiq emas (holat: {row.status})."
        sig = self.journal.get_signal(sid)
        risk = self.risk.evaluate(sig, self._account_state(row.symbol))
        if not risk.approved:
            log.info("RiskVeto", id=sid, symbol=row.symbol, reasons=risk.reasons)
            return f"⛔️ #{sid} risk rad etdi: {', '.join(risk.reasons) or 'limit'}"
        result = self.execution.execute(sig, risk, take_profit=sig.tp3)
        if result.status != "EXECUTED":
            log.info("ManualExecFailed", id=sid, status=result.status,
                     reason=result.reason, retcode=result.retcode)
            if result.retcode == MARKET_CLOSED:
                return (f"❌ #{sid} {row.symbol} — bozor hozir yopiq (dam olish kuni yoki "
                        f"sessiya tashqarisida). Bozor ochilganda tugmani qayta bosing.")
            return f"❌ #{sid} ochilmadi: {result.reason}"
        self.journal.record_execution(sid, result.ticket, result.volume, result.fill_price)
        log.info("ManualExecuted", id=sid, symbol=row.symbol, ticket=result.ticket,
                 lots=result.volume)
        return (f"✅ Order ochildi — #{sid} <b>{row.symbol}</b> {row.direction}\n"
                f"📦 Lot: {result.volume} · 🎫 Ticket: {result.ticket}\n"
                f"🛑 Stop + 🎯 TP3 backstop qo'yildi · bot 40/40/20 boshqaradi")

    # ── outcome tracking for open trades ──────────────────────────────────
    def check_outcomes(self) -> None:
        # Price of record is the DATA SOURCE (Yahoo/MT5), not the broker — in
        # dry-run the PaperBroker has no quotes. Fetch each symbol's latest bar
        # once per cycle and use its high/low so intrabar TP/SL hits are caught.
        cache: dict[tuple[str, str], object] = {}
        for row in self.journal.open_trades():
            try:
                key = (row.symbol, row.timeframe)      # track on the trade's own TF
                if key not in cache:                   # enough bars to also draw a chart
                    cache[key] = self.source.fetch(row.symbol, row.timeframe, 80)
                df = cache[key]
                hi, lo = float(df["high"].iloc[-1]), float(df["low"].iloc[-1])
                self._resolve(row, hi, lo, df)
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

    def _resolve(self, row, hi: float, lo: float, df=None) -> None:
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

        # ── ATR-trailing runner (post-TP2): lock profit instead of sitting at
        # breakeven — a reversal closes the runner in profit, not at 0.
        atr = (float(df["atr"].iloc[-1])
               if df is not None and "atr" in df and float(df["atr"].iloc[-1]) > 0
               else None)
        trail_mult = float(self.mgmt.get("trail_atr_mult", 0) or 0)
        if row.status == "tp2" and trail_mult and atr:
            trail = (hi - trail_mult * atr) if long else (lo + trail_mult * atr)
            better = max(e, trail) if long else min(e, trail)
            if better != eff_sl:
                eff_sl = better
                if row.ticket:                       # keep the broker stop in sync
                    self._broker_op(lambda: self.broker.modify(
                        row.ticket, stop_loss=eff_sl))
        stop_hit = (lo <= eff_sl) if long else (hi >= eff_sl)

        if stop_hit:
            if row.status == "open":
                self._close(row, "stopped", -1.0, df)
                return
            booked = w1 * sign * (row.tp1 - e) / r
            if row.status == "tp2":
                booked += w2 * sign * (row.tp2 - e) / r
            rem = {"tp1": w2 + w3, "tp2": w3}[row.status]   # runner still live
            booked += rem * sign * (eff_sl - e) / r          # 0 at BE, >0 when trailed
            trailed = (eff_sl > e) if long else (eff_sl < e)
            self._close(row, "trailed" if trailed else "breakeven",
                        round(booked, 2), df)
        elif reached(row.tp3) and row.status == "tp2":
            total = sign * (w1 * (row.tp1 - e) + w2 * (row.tp2 - e)
                            + w3 * (row.tp3 - e)) / r
            self._close(row, "tp3", round(total, 2), df)
        elif reached(row.tp2) and row.status == "tp1":
            booked = sign * (w1 * (row.tp1 - e) + w2 * (row.tp2 - e)) / r
            self._advance(row, "tp2", round(booked, 2), df)
        elif reached(row.tp1) and row.status == "open":
            self._advance(row, "tp1", round(w1 * sign * (row.tp1 - e) / r, 2), df)
        elif row.status == "open":
            self._early_exit(row, df, e, r, sign)

    def _early_exit(self, row, df, e: float, r: float, sign: float) -> None:
        """Cut a dead or invalidated trade BEFORE the full stop (risk.yaml
        trade_management). Runs only when the bar hit neither a TP nor the stop,
        so booking at the current close is safe."""
        if df is None or "close" not in df:
            return
        close = float(df["close"].iloc[-1])
        unreal = max(-1.0, sign * (close - e) / r)     # stop path handles < −1R

        # 1 — structure invalidation: an opposite CHOCH says the setup's premise
        # is gone; waiting for the stop just donates the rest of the R.
        if self.mgmt.get("invalidation_exit", True) and len(df) >= 30:
            try:
                st = self.structure.analyze(row.symbol, df)
                against = "bearish" if row.direction == "BUY" else "bullish"
                if st.choch and st.choch_direction == against:
                    log.info("EarlyExit", id=row.id, kind="invalidated",
                             r=round(unreal, 2))
                    self._close(row, "invalidated", round(unreal, 2), df)
                    return
            except Exception as exc:                   # analysis must never kill the loop
                log.warning("InvalidationCheckFailed", id=row.id, error=str(exc))

        # 2 — time-stop: N bars without ever printing TP1 and still below the
        # progress floor = a dead trade occupying risk budget.
        bars_limit = int(self.mgmt.get("time_stop_bars", 0) or 0)
        if bars_limit and row.created_at:
            tf_min = _TF_MIN.get(row.timeframe, 60)
            bars_open = (time.time() - row.created_at) / (tf_min * 60)
            if bars_open >= bars_limit and \
                    unreal < float(self.mgmt.get("time_stop_min_r", 0.5)):
                log.info("EarlyExit", id=row.id, kind="stale",
                         bars=int(bars_open), r=round(unreal, 2))
                self._close(row, "stale", round(unreal, 2), df)

    def _close(self, row, status: str, result_r: float, df=None) -> None:
        self.journal.close_signal(row.id, status, result_r)
        if row.ticket:
            self._broker_op(lambda: self.broker.close(row.ticket))   # close remainder
        self.notifier.on_outcome(row, status, result_r, df=df, timeframe=row.timeframe)

    def _advance(self, row, status: str, booked_r: float, df=None) -> None:
        """Book a partial scale-out and keep the runner live. When a real position
        exists (manual trade), scale it out on the broker too so broker and journal
        never disagree: close 40% of the original at TP1 (stop → breakeven) and
        another 40% at TP2; the runner rides to the TP3 backstop."""
        self.journal.advance(row.id, status, booked_r)
        if row.ticket:
            if status == "tp1":
                self._broker_op(lambda: self.execution.partial_close(row.ticket, 0.40))
                self._broker_op(lambda: self.execution.move_to_breakeven(
                    row.ticket, row.entry))
            elif status == "tp2":
                self._broker_op(lambda: self.execution.partial_close(  # 0.4 of original
                    row.ticket, round(0.40 / 0.60, 4)))
        self.notifier.on_outcome(row, status, booked_r, df=df, timeframe=row.timeframe)

    @staticmethod
    def _broker_op(fn) -> None:
        """Run a broker management call; never let a broker hiccup crash the outcome
        loop, which also shadow-tracks untraded signals."""
        try:
            fn()
        except Exception as exc:
            log.warning("BrokerOpFailed", error=str(exc))

    def _account_state(self, symbol: str | None = None) -> AccountState:
        """The risk engine's view of the account.

        Two very different books, one per mode:
          • dry-run (paper / mt5-data) → the JOURNAL shadow book. Every signal is
            tracked as an open trade and its paper outcome feeds realized_r, so the
            AI layer gets a labelled history. Correct when NO real order is placed.
          • trade mode (auto-execute or the Avto-savdo button enabled) → the REAL
            broker: open_positions from broker.positions(), balance/equity from
            account_info(), and realized loss ONLY from trades that carried a real
            ticket. Otherwise the ~18 never-filled shadow signals (and their −R
            paper outcomes) would trip the open-trade / heat / loss caps and veto
            every live trade — the bug that blocked the first button press.
        """
        if self._trade_mode():
            return self._live_account_state(symbol)
        return self._shadow_account_state()

    def _contract_map(self, symbol: str | None) -> dict[str, float]:
        """Per-symbol units-per-lot for the risk engine. Config is the base; in
        trade mode the LIVE broker value for the signal's symbol wins (cached in
        the adapter — one rpyc call per symbol per session)."""
        contracts = dict(self._contracts)
        if symbol and self._trade_mode():
            try:
                live = float(self.broker.contract_size(symbol) or 0.0)
                if live > 0:
                    contracts[symbol] = live
            except Exception as exc:
                log.warning("ContractSizeFailed", symbol=symbol, error=str(exc))
        return contracts

    def _trade_mode(self) -> bool:
        """True when a real order can actually be placed — the scanner auto-trades
        or the Telegram Avto-savdo button is live (mt5-manual / mt5-live)."""
        return self.auto_execute or self.notifier.trade_enabled

    def _shadow_account_state(self) -> AccountState:
        positions = [
            OpenPosition(symbol=row.symbol, direction=row.direction,
                         risk_pct=self.risk.risk_pct)
            for row in self.journal.open_trades()]
        return AccountState(
            balance=self.balance, equity=self.balance,
            open_positions=positions,
            realized_pnl_today_pct=self.journal.realized_r(86400) * self.risk.risk_pct,
            realized_pnl_week_pct=self.journal.realized_r(7 * 86400) * self.risk.risk_pct,
            contract_size=100000.0, contract_sizes=dict(self._contracts))

    def _live_account_state(self, symbol: str | None = None) -> AccountState:
        # Each real position counts as one standard risk unit against the heat /
        # exposure / open-trade caps — exactly how a new trade is sized, so N open
        # positions = N × risk_pct of heat.
        positions = [
            OpenPosition(symbol=p.symbol, direction=p.direction,
                         risk_pct=self.risk.risk_pct)
            for p in self._broker_positions()]
        balance, equity = self._broker_balance()
        return AccountState(
            balance=balance, equity=equity,
            open_positions=positions,
            realized_pnl_today_pct=self.journal.realized_r(
                86400, executed_only=True) * self.risk.risk_pct,
            realized_pnl_week_pct=self.journal.realized_r(
                7 * 86400, executed_only=True) * self.risk.risk_pct,
            contract_size=100000.0, contract_sizes=self._contract_map(symbol))

    def _broker_positions(self) -> list:
        try:
            return self.broker.positions()
        except Exception as exc:
            log.warning("BrokerPositionsFailed", error=str(exc))
            return []

    def _broker_balance(self) -> tuple[float, float]:
        """Real (balance, equity) from the broker; fall back to the configured
        balance if the adapter can't report (e.g. PaperBroker, bridge hiccup)."""
        info = getattr(self.broker, "account_info", None)
        if info is not None:
            try:
                balance, equity = info()
                if balance > 0:
                    return balance, equity
            except Exception as exc:
                log.warning("BrokerAccountInfoFailed", error=str(exc))
        return self.balance, self.balance

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

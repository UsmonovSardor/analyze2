"""Monitoring & Health Engine (SRS doc 24).

Pragmatic for the single-server dry-run: the engine tracks scan liveness, feed
health, consecutive errors and host resources, produces a health snapshot, and
decides when to raise a Telegram alert (rate-limited). Docker's
`restart: unless-stopped` already handles process crashes; this layer catches the
subtler failures — a dead data feed, a stalled scan loop, a full disk.

Resource metrics are best-effort (psutil if present; disk via stdlib) so the
engine never crashes the bot it is meant to watch.
"""
from __future__ import annotations

import shutil
import time

from pydantic import BaseModel

from ..core.logging import get_logger

log = get_logger("monitoring")


class HealthReport(BaseModel):
    status: str                      # HEALTHY | DEGRADED | FAILED
    uptime_seconds: int
    seconds_since_scan: int | None
    consecutive_errors: int
    feed_ok: bool
    signals_today: int
    open_trades: int
    cpu_pct: float | None = None
    mem_pct: float | None = None
    disk_pct: float | None = None


class HealthMonitor:
    def __init__(self, *, error_alert_threshold: int = 3,
                 stale_scan_factor: float = 3.0,
                 alert_cooldown_sec: int = 2 * 3600) -> None:
        self._start = time.time()
        self._last_scan: float | None = None
        self._consecutive_errors = 0
        self._feed_ok = True
        self.error_alert_threshold = error_alert_threshold
        self.stale_scan_factor = stale_scan_factor
        self.alert_cooldown_sec = alert_cooldown_sec
        self._last_alert = 0.0

    # ── recorders (called by the runtime) ─────────────────────────────────
    def record_scan(self, *, signals: int, errors: int, feed_ok: bool) -> None:
        self._last_scan = time.time()
        self._feed_ok = feed_ok
        if errors > 0 and signals == 0 and not feed_ok:
            self._consecutive_errors += 1
        else:
            self._consecutive_errors = 0

    def record_loop_error(self) -> None:
        self._consecutive_errors += 1

    # ── snapshot ──────────────────────────────────────────────────────────
    def snapshot(self, *, signals_today: int, open_trades: int,
                 scan_interval: int = 1800) -> HealthReport:
        now = time.time()
        since = int(now - self._last_scan) if self._last_scan else None
        cpu, mem, disk = self._resources()

        status = "HEALTHY"
        if self._consecutive_errors >= self.error_alert_threshold or not self._feed_ok:
            status = "DEGRADED"
        if since is not None and since > scan_interval * self.stale_scan_factor:
            status = "FAILED"                 # scan loop stalled
        if disk is not None and disk >= 95:
            status = "FAILED"                 # disk almost full

        return HealthReport(
            status=status, uptime_seconds=int(now - self._start),
            seconds_since_scan=since, consecutive_errors=self._consecutive_errors,
            feed_ok=self._feed_ok, signals_today=signals_today,
            open_trades=open_trades, cpu_pct=cpu, mem_pct=mem, disk_pct=disk)

    def should_alert(self, report: HealthReport) -> bool:
        """True at most once per cooldown when health is not HEALTHY."""
        if report.status == "HEALTHY":
            return False
        if time.time() - self._last_alert < self.alert_cooldown_sec:
            return False
        self._last_alert = time.time()
        return True

    @staticmethod
    def _resources() -> tuple[float | None, float | None, float | None]:
        cpu = mem = None
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
        except Exception:
            pass
        try:
            usage = shutil.disk_usage("/")
            disk = round(100 * usage.used / usage.total, 1)
        except Exception:
            disk = None
        return cpu, mem, disk

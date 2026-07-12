"""Red-folder news guard (configs/news.yaml).

High-impact macro releases (NFP, FOMC, CPI…) whip spreads and invalidate
technical setups — the ICT models in the catalog flatly forbid trading near
them. This guard blocks NEW signals and button executions inside a ±window
around high-impact events for the symbol's currencies.

Data: ForexFactory's public weekly calendar JSON (faireconomy mirror), cached
in-process. FAIL-OPEN by design: if the feed is unreachable the bot trades
normally and logs — a missing calendar must never halt a working system.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import requests

from ..core import config
from ..core.logging import get_logger

log = get_logger("data.news")

_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_CACHE_TTL = 6 * 3600                      # calendar changes rarely intra-day


def currencies_for(symbol: str) -> set[str]:
    """FX pair → both legs; metals react to the USD leg."""
    if symbol.startswith(("XAU", "XAG")):
        return {"USD"}
    return {symbol[:3], symbol[3:6]} if len(symbol) >= 6 else {symbol}


class NewsGuard:
    def __init__(self) -> None:
        try:
            cfg = config.load("news")
        except Exception:
            cfg = {}
        self.enabled: bool = bool(cfg.get("enabled", True)) \
            and config.env("BL_NEWS_DISABLED", "") != "1"
        self.window = timedelta(minutes=int(cfg.get("window_minutes", 30)))
        self.impacts: set[str] = {str(i) for i in cfg.get("impacts", ["High"])}
        self._events: list[tuple[datetime, str, str]] = []   # (ts, currency, title)
        self._fetched_at: float = 0.0

    def _refresh(self) -> None:
        if time.time() - self._fetched_at < _CACHE_TTL:
            return
        self._fetched_at = time.time()                 # even on failure: no hammering
        try:
            rows = requests.get(_URL, timeout=10).json()
            events = []
            for r in rows:
                if str(r.get("impact", "")) not in self.impacts:
                    continue
                ts = datetime.fromisoformat(str(r.get("date", "")))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                events.append((ts.astimezone(timezone.utc),
                               str(r.get("country", "")).upper(),
                               str(r.get("title", ""))[:60]))
            self._events = events
            log.info("NewsCalendarLoaded", events=len(events))
        except Exception as exc:                       # fail-open
            log.warning("NewsCalendarFailed", error=str(exc))

    def blackout(self, symbol: str, now: datetime | None = None) -> str | None:
        """Event title when `symbol` is inside a red-folder window, else None."""
        if not self.enabled:
            return None
        self._refresh()
        if not self._events:
            return None
        now = now or datetime.now(timezone.utc)
        legs = currencies_for(symbol)
        for ts, ccy, title in self._events:
            if ccy in legs and abs(ts - now) <= self.window:
                return f"{ccy} {title} ({ts:%H:%M} UTC)"
        return None

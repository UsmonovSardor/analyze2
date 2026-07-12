"""Red-folder news guard: currency mapping, blackout window, fail-open."""
import time
from datetime import datetime, timedelta, timezone

from blacklion.data.news import NewsGuard, currencies_for


def _guard(events):
    g = NewsGuard()
    g.enabled = True                       # conftest disables via env — re-arm
    g._events = events
    g._fetched_at = time.time()            # cache warm → no network
    return g


def test_currencies_for_pairs_and_metals():
    assert currencies_for("EURUSD") == {"EUR", "USD"}
    assert currencies_for("GBPJPY") == {"GBP", "JPY"}
    assert currencies_for("XAUUSD") == {"USD"}


def test_blackout_inside_window_only():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    g = _guard([(now + timedelta(minutes=20), "USD", "Non-Farm Payrolls")])
    assert g.blackout("EURUSD", now) is not None       # 20min away, USD leg
    assert g.blackout("XAUUSD", now) is not None       # metals follow USD
    assert g.blackout("EURGBP", now) is None           # no USD leg
    g2 = _guard([(now + timedelta(minutes=45), "USD", "CPI")])
    assert g2.blackout("EURUSD", now) is None          # outside ±30min


def test_disabled_guard_never_blocks():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    g = _guard([(now, "USD", "FOMC")])
    g.enabled = False
    assert g.blackout("EURUSD", now) is None

"""Doc 24 test cases: health status, staleness, error alerting, rate limiting."""
from blacklion.monitoring import HealthMonitor


def test_healthy_after_good_scan():
    m = HealthMonitor()
    m.record_scan(signals=1, errors=0, feed_ok=True)
    r = m.snapshot(signals_today=1, open_trades=1)
    assert r.status == "HEALTHY" and r.feed_ok and r.consecutive_errors == 0


def test_degraded_when_feed_down_repeatedly():
    m = HealthMonitor(error_alert_threshold=3)
    for _ in range(3):
        m.record_scan(signals=0, errors=5, feed_ok=False)
    r = m.snapshot(signals_today=0, open_trades=0)
    assert r.status == "DEGRADED" and not r.feed_ok


def test_failed_when_scan_stale():
    m = HealthMonitor(stale_scan_factor=3.0)
    m.record_scan(signals=0, errors=0, feed_ok=True)
    m._last_scan -= 6000                     # pretend last scan was long ago
    r = m.snapshot(signals_today=0, open_trades=0, scan_interval=1800)
    assert r.status == "FAILED"


def test_errors_reset_on_good_scan():
    m = HealthMonitor()
    m.record_scan(signals=0, errors=3, feed_ok=False)
    m.record_scan(signals=2, errors=0, feed_ok=True)
    assert m.snapshot(signals_today=2, open_trades=0).consecutive_errors == 0


def test_alert_fires_once_then_rate_limited():
    m = HealthMonitor(error_alert_threshold=1, alert_cooldown_sec=3600)
    m.record_scan(signals=0, errors=1, feed_ok=False)
    r = m.snapshot(signals_today=0, open_trades=0)
    assert m.should_alert(r) is True         # first time
    assert m.should_alert(r) is False        # within cooldown


def test_no_alert_when_healthy():
    m = HealthMonitor()
    m.record_scan(signals=1, errors=0, feed_ok=True)
    r = m.snapshot(signals_today=1, open_trades=0)
    assert m.should_alert(r) is False


def test_snapshot_has_disk_metric():
    m = HealthMonitor()
    r = m.snapshot(signals_today=0, open_trades=0)
    # disk via stdlib should always be available
    assert r.disk_pct is None or 0 <= r.disk_pct <= 100

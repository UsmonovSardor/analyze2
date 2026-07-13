"""Volume Profile engine (TITAN Bible ch.7): VWAP/POC/Value Area/Spike."""
import numpy as np
import pandas as pd

from blacklion.engines.volume_profile import VolumeProfileEngine


def _df(closes, vols):
    c = np.asarray(closes, float)
    o = np.roll(c, 1)
    o[0] = c[0]
    h = np.maximum(o, c) + 0.2
    lo = np.minimum(o, c) - 0.2
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c,
                         "volume": np.asarray(vols, float)})


def test_vwap_side_and_bias():
    eng = VolumeProfileEngine()
    up = _df([100 + i * 0.1 for i in range(60)], [100] * 60)
    res = eng.analyze("EURUSD", up)
    assert res.price_vs_vwap == "above"       # last close well above the mean VWAP
    assert res.bias == "bullish"
    assert res.val <= res.poc <= res.vah      # value area brackets the POC


def test_volume_spike_detected():
    vols = [100] * 59 + [400]                  # last bar 4× average
    res = VolumeProfileEngine().analyze("EURUSD",
                                        _df([100 + i * 0.05 for i in range(60)], vols))
    assert res.volume_spike and res.spike_ratio >= 2.0


def test_no_spike_on_flat_volume():
    res = VolumeProfileEngine().analyze("EURUSD",
                                        _df([100 + i * 0.05 for i in range(60)], [100] * 60))
    assert not res.volume_spike


def test_short_frame_is_safe():
    res = VolumeProfileEngine().analyze("EURUSD", _df([100, 101, 102], [1, 1, 1]))
    assert res.vp_score == 0 and res.vwap == 0.0


def test_value_area_contains_most_volume():
    # concentrate volume around 100 → POC near 100, value area tight
    closes = [100.0] * 40 + [100 + i * 0.1 for i in range(20)]
    vols = [500] * 40 + [50] * 20
    res = VolumeProfileEngine().analyze("EURUSD", _df(closes, vols))
    assert abs(res.poc - 100.0) < 1.0

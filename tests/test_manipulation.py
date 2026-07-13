"""Manipulation / Trap / Inducement engine (TITAN Bible ch.8)."""
from types import SimpleNamespace

import pandas as pd

from blacklion.engines.manipulation import ManipulationEngine


def _frame(rows, vols=None):
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df["volume"] = 100.0 if vols is None else vols
    return df


def _base(n=30, level=100.0):
    # a tight range hugging `level` so prior swing high/low are well-defined
    return [(level, level + 0.3, level - 0.3, level) for _ in range(n)]


def test_bull_trap_detected_and_traps_buyers():
    rows = _base(28)
    # a bar wicks above the 100.3 range high but closes back inside → bull trap
    rows.append((100.2, 101.5, 100.1, 100.1))
    rows.append((100.1, 100.3, 99.9, 100.0))
    res = ManipulationEngine().analyze("EURUSD", _frame(rows))
    assert res.bull_trap and res.trapped_direction == "BUY"


def test_bear_trap_detected_and_traps_sellers():
    rows = _base(28)
    rows.append((99.8, 99.9, 98.5, 99.9))       # wick below range low, closes back in
    rows.append((99.9, 100.1, 99.7, 100.0))
    res = ManipulationEngine().analyze("EURUSD", _frame(rows))
    assert res.bear_trap and res.trapped_direction == "SELL"


def test_strong_breakout_on_volume_is_not_a_trap():
    rows = _base(28)
    rows.append((100.2, 101.5, 100.2, 101.4))   # broke AND closed above on big volume
    rows.append((101.4, 101.8, 101.3, 101.7))
    vols = [100.0] * 28 + [500.0, 500.0]        # expanding volume → genuine
    res = ManipulationEngine().analyze("EURUSD", _frame(rows, vols))
    assert not res.bull_trap


def test_inducement_from_liquidity_stop_hunt():
    rows = _base(34)
    liq = SimpleNamespace(stop_hunt=True, liquidity_swept=True)
    res = ManipulationEngine().analyze("EURUSD", _frame(rows), liquidity=liq)
    assert res.inducement and res.manip_score >= 30


def test_short_frame_is_safe():
    res = ManipulationEngine().analyze("EURUSD", _frame(_base(5)))
    assert not res.bull_trap and not res.bear_trap and res.manip_score == 0

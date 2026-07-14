"""Multi-Timeframe cascade + Conflict Engine (TITAN Bible ch.6)."""
from types import SimpleNamespace

from blacklion.engines.mtf import MTFResult, MultiTimeframe


def _trend(bullish: bool, bearish: bool):
    return SimpleNamespace(trend=SimpleNamespace(bullish=bullish, bearish=bearish))


class _Structure:
    """Stub — returns a preset trend per timeframe so the test exercises the
    cascade logic, not the (separately tested) structure classifier."""
    def __init__(self, per_tf):
        self.per_tf = per_tf

    def analyze(self, symbol, df):
        return self.per_tf[df]           # df is the tf label in this stub


class _Src:
    def fetch(self, symbol, tf, n):
        return tf                        # pass the tf label through as the "df"


def _mtf(per_tf):
    return MultiTimeframe(structure=_Structure(per_tf))


def test_higher_tfs_excludes_entry_and_below():
    m = MultiTimeframe()
    assert m.higher_tfs("M15") == ["D1", "H4", "H1"]
    assert m.higher_tfs("H1") == ["D1", "H4"]
    assert m.higher_tfs("D1") == []


def test_aligned_cascade_scores_full():
    per = {"D1": _trend(True, False), "H4": _trend(True, False),
           "H1": _trend(True, False)}
    res = _mtf(per).analyze(_Src(), "EURUSD", "M15")
    assert res.total == 3
    assert res.agrees("BUY") == 3
    assert not res.conflicts("BUY")
    assert res.score("BUY") == 1.0


def test_one_opposing_tf_is_tolerated_two_conflicts():
    # softened 6.9: a lone opposing TF is NOT a conflict; a majority is
    one = {"D1": _trend(False, True),          # only D1 bearish
           "H4": _trend(True, False), "H1": _trend(True, False)}
    res = _mtf(one).analyze(_Src(), "EURUSD", "M15")
    assert res.opposing("BUY") == 1
    assert not res.conflicts("BUY")            # default min_opposing=2 → tolerated
    assert res.conflicts("BUY", min_opposing=1)   # strict mode still available

    two = {"D1": _trend(False, True), "H4": _trend(False, True),
           "H1": _trend(True, False)}
    res2 = _mtf(two).analyze(_Src(), "EURUSD", "M15")
    assert res2.opposing("BUY") == 2
    assert res2.conflicts("BUY")               # ≥2 oppose → reject


def test_missing_tf_is_skipped_not_fatal():
    class Partial:
        def fetch(self, symbol, tf, n):
            if tf == "D1":
                raise RuntimeError("no daily")
            return tf
    per = {"H4": _trend(True, False), "H1": _trend(True, False)}
    res = MultiTimeframe(structure=_Structure(per)).analyze(Partial(), "EURUSD", "M15")
    assert res.total == 2                       # D1 skipped, H4+H1 counted


def test_empty_result_scores_neutral():
    assert MTFResult().score("BUY") == 0.5

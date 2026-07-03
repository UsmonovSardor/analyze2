"""Doc 15 test cases: mandatory conditions, confluence gate, signal levels.

Uses the full pipeline so the Rule Engine is tested against real engine outputs.
"""
from blacklion.engines.pipeline import SignalPipeline
from tests.helpers import df_from_ohlc, df_from_closes, zigzag

PIPE = SignalPipeline()


def _flat(n: float, count: int) -> list[tuple]:
    return [(n, n + 0.2, n - 0.2, n) for _ in range(count)]


def bullish_setup() -> list[tuple]:
    """Uptrend with HH/HL, a fresh bullish OB + FVG, price pulling into discount."""
    rows: list[tuple] = []
    # rising staircase → bullish structure with clean swings
    for base in (100, 104, 108, 112, 116):
        rows.append((base, base + 0.3, base - 1.2, base - 0.8))   # pullback low
        rows.append((base - 0.8, base + 3.0, base - 1.0, base + 2.6))  # push up
        rows += [(base + 2.6, base + 2.9, base + 2.3, base + 2.6) for _ in range(2)]
    return rows


def test_sideways_market_is_no_trade():
    dec = PIPE.run("EURUSD", df_from_ohlc(_flat(1.1000, 60)))
    assert dec.decision == "NO TRADE"


def test_counter_trend_htf_conflict_rejected():
    # Safety-critical guarantee: a bullish setup against a bearish HTF never trades.
    df = df_from_ohlc(bullish_setup())
    long_ok = PIPE.run("EURUSD", df, htf_bullish=True)
    conflict = PIPE.run("EURUSD", df, htf_bullish=False)
    assert conflict.decision == "NO TRADE"
    # HTF is the ONLY thing that changed, so a conflicting HTF must not be MORE
    # permissive than an aligned one.
    if long_ok.decision == "BUY":
        assert any("HTF" in r for r in conflict.rejected)


def test_signal_has_valid_level_ordering_when_generated():
    df = df_from_ohlc(bullish_setup())
    dec = PIPE.run("XAUUSD", df, htf_bullish=True)
    if dec.signal is not None:                        # setup may or may not clear the gate
        s = dec.signal
        if s.direction == "BUY":
            assert s.stop_loss < s.entry < s.tp1 < s.tp2 < s.tp3
        else:
            assert s.stop_loss > s.entry > s.tp1 > s.tp2 > s.tp3
        assert s.rr >= 2.0                            # risk.yaml minimum_rr
        assert 0 <= s.confidence <= 100


def test_decision_is_deterministic():
    df = df_from_ohlc(bullish_setup())
    a = PIPE.run("XAUUSD", df, htf_bullish=True)
    b = PIPE.run("XAUUSD", df, htf_bullish=True)
    assert a.model_dump() == b.model_dump()


def test_confluence_never_exceeds_100():
    df = df_from_closes(zigzag([100, 110, 105, 118, 112, 127, 120, 136]))
    dec = PIPE.run("XAUUSD", df, htf_bullish=True)
    assert 0 <= dec.confluence_score <= 100

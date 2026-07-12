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


def test_reasons_carry_real_data_values():
    """User demand: no canned identical reasons — every signal's Tahlil lines must
    embed the actual numbers the engines saw (prices, strength, RSI, ATR).
    Exercises _reasons directly so the path is ALWAYS covered."""
    import pandas as pd

    from blacklion.engines.fvg import FairValueGap, FVGResult
    from blacklion.engines.ict import ICTResult
    from blacklion.engines.liquidity import LiquidityResult
    from blacklion.engines.market_structure import StructureResult
    from blacklion.engines.market_structure.service import Trend
    from blacklion.engines.order_block import OrderBlock
    from blacklion.engines.rule_engine.service import RuleEngine

    n = 30
    df = pd.DataFrame({
        "close": [1.1000 + i * 0.001 for i in range(n)],
        "rsi": [40.0 + i * 0.5 for i in range(n)],
        "ema50": [1.0980 + i * 0.001 for i in range(n)],
        "ema200": [1.0950 + i * 0.001 for i in range(n)],
        "atr": [0.0021] * n,
    })
    structure = StructureResult(
        symbol="EURUSD", trend=Trend.BULLISH, structure="HH-HL",
        bos=True, bos_direction="bullish", choch=False,
        strength=78, quality="A", confidence=80, last_swing_low=1.1381)
    liquidity = LiquidityResult(
        symbol="EURUSD", buy_side_liquidity=False, sell_side_liquidity=True,
        liquidity_swept=True, sweep_direction="bullish", stop_hunt=True,
        nearest_pool=1.1378, liquidity_score=72, quality="A", confidence=75)
    ob = OrderBlock(type="bullish", index=25, price_low=1.1390, price_high=1.1408,
                    fresh=True, mitigated=False, score=86, quality="A+", confidence=85)
    fvg = FVGResult(symbol="EURUSD", nearest=FairValueGap(
        type="bullish", index=26, gap_low=1.1395, gap_high=1.1402, size=0.0007,
        filled_pct=30.0, filled=False, score=74, quality="A", confidence=70))
    ict = ICTResult(symbol="EURUSD", premium_discount="Discount",
                    equilibrium=1.1421, ote=True, ote_zone=(1.1385, 1.1401),
                    kill_zone="london", ict_score=68, quality="B")

    reasons = RuleEngine()._reasons("EURUSD", df, "BUY", structure, liquidity,
                                    ob, fvg, ict)
    text = " ".join(reasons)
    assert "kuch 78/100" in text                        # structure strength value
    assert "1.1381" in text                             # protective swing price
    assert "1.139" in text and "score 86" in text       # OB band + score
    assert "30% to'ldirilgan" in text                   # FVG fill state
    assert "equilibrium 1.1421" in text                 # ICT location value
    assert "London kill zone" in text
    assert "RSI" in text and "ATR" in text
    # a different tape must produce different text (no canned reasons)
    df2 = df.assign(rsi=[70.0 - i for i in range(n)], atr=[0.005] * n)
    reasons2 = RuleEngine()._reasons("EURUSD", df2, "BUY", structure, liquidity,
                                     ob, fvg, ict)
    assert reasons != reasons2


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


def test_stored_signal_rr_survives_tick_rounding():
    """The risk engine recomputes RR from the STORED (rounded) entry/stop/tp2, so
    tick-rounding must never drop it below the minimum and veto our own signal.

    Regression: a JPN225 (digits=0) 2.0R target was stored at 68606 instead of
    68605 → 1.99R → "RR 1.99 below minimum 2.0", blocking the Avto-savdo button.
    Sweep fractional entries (the source of the 1-tick drift) on an integer-digit
    instrument; every stored signal must still clear min_rr when re-derived.
    """
    from types import SimpleNamespace

    from blacklion.engines.rule_engine.service import RuleEngine

    eng = RuleEngine()
    min_rr = float(eng.risk["minimum_rr"])
    df = df_from_ohlc(_flat(68900.0, 30))
    for frac in range(100):                       # 68898.00 … 68898.99
        close = 68898.0 + frac / 100.0
        df.loc[df.index[-1], "close"] = close
        structure = SimpleNamespace(
            last_swing_high=69040.0, last_swing_low=68760.0, strength=70)
        sig = eng._build_signal("JPN225", df, "SELL", structure,
                                ob=None, fvg=None, confluence=80)
        if sig is None:
            continue
        r = abs(sig.entry - sig.stop_loss)
        rr = abs(sig.tp2 - sig.entry) / r         # exactly how RiskEngine recomputes
        assert rr >= min_rr, f"close={close}: stored RR {rr:.4f} < {min_rr}"
        assert sig.entry > sig.tp1 > sig.tp2 > sig.tp3   # SELL ordering intact


def test_decision_is_deterministic():
    df = df_from_ohlc(bullish_setup())
    a = PIPE.run("XAUUSD", df, htf_bullish=True)
    b = PIPE.run("XAUUSD", df, htf_bullish=True)
    assert a.model_dump() == b.model_dump()


def test_confluence_never_exceeds_100():
    df = df_from_closes(zigzag([100, 110, 105, 118, 112, 127, 120, 136]))
    dec = PIPE.run("XAUUSD", df, htf_bullish=True)
    assert 0 <= dec.confluence_score <= 100

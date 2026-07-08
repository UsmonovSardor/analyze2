"""Signal chart renderer: produces a valid PNG and never raises into the caller."""
import pytest

from blacklion.engines.rule_engine import Signal
from blacklion.telegram.chart import render_signal_chart
from tests.helpers import df_from_closes

_PNG = b"\x89PNG\r\n\x1a\n"


def _sig(direction="BUY") -> Signal:
    return Signal(symbol="EURUSD", direction=direction, entry=1.1000,
                  stop_loss=1.0980, tp1=1.1010, tp2=1.1050, tp3=1.1100, rr=2.5,
                  confidence=80, confluence_score=70, reasons=["x"])


def test_render_returns_png_bytes():
    pytest.importorskip("matplotlib")
    df = df_from_closes([1.10 + 0.0003 * i for i in range(90)])
    png = render_signal_chart(_sig(), df, "H1")
    assert png is not None and png[:8] == _PNG and len(png) > 1000


def test_render_sell_direction_ok():
    pytest.importorskip("matplotlib")
    df = df_from_closes([1.11 - 0.0003 * i for i in range(90)])
    png = render_signal_chart(_sig("SELL"), df, "M15")
    assert png is not None and png[:8] == _PNG


def test_render_degrades_to_none_on_bad_data():
    # a frame missing OHLC columns must not raise — the signal still ships as text
    import pandas as pd
    assert render_signal_chart(_sig(), pd.DataFrame({"nope": [1, 2, 3]}), "H1") is None

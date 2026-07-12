# Strategy catalog — source of truth for the deterministic detectors

These four files are the knowledge base ported from the paused "analyze" bot
(github.com/UsmonovSardor/analyze, `skill/`), where an LLM read them as a system
prompt. In BLACK LION they are **documentation only** — each named strategy is
implemented as a deterministic detector in `blacklion/engines/strategies/`
(SRS "no black box"), citing the section it implements:

| detector                | file                     | catalog section          |
|-------------------------|--------------------------|--------------------------|
| Trend Pullback (A)      | `setup_a.py`             | strategy.md §Setup A     |
| Range Breakout (B)      | `setup_b.py`             | strategy.md §Setup B     |
| regime classifier       | `regime.py`              | strategy.md §Market Regime |
| 7-factor scorecard      | `scorecard.py`           | strategy.md §Confluence Scorecard |
| candle patterns         | `candles.py`             | candlestick-patterns.md, price-action.md |

Phase-2 candidates (HTF-expressible): ICT Turtle Soup, Unicorn, AMD/PO3.
Deferred (need 5m/1m data): Judas Swing, Venom, MMXM, LTF scalp models.

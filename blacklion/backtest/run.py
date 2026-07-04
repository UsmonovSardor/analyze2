"""Backtest CLI — run the strategy over real historical data.

    python -m blacklion.backtest.run XAUUSD          # H1, ~2 years of daily bars
    python -m blacklion.backtest.run EURUSD H1 700
    python -m blacklion.backtest.run all D1 500       # every configured symbol

Fetches candles via YahooSource (no credentials), replays them through the live
pipeline, and prints a performance report. Read-only — never places orders.
"""
from __future__ import annotations

import sys

from ..core import config
from ..data.sources import YahooSource
from .engine import Backtester, BacktestReport


def _report_text(r: BacktestReport) -> str:
    m = r.metrics
    lines = [
        f"═══ {r.symbol}  ({r.bars} bars, {m.trades} trades) ═══",
        f"  Win rate     : {m.win_rate}%  ({m.wins}W / {m.losses}L)",
        f"  Net          : {m.net_r:+.2f}R      Expectancy: {m.expectancy:+.3f}R/trade",
        f"  Profit factor: {m.profit_factor}     Sharpe: {m.sharpe}",
        f"  Avg win/loss : {m.avg_win_r:+.2f}R / {m.avg_loss_r:+.2f}R",
        f"  Max drawdown : {m.max_drawdown_r:.2f}R",
        f"  Best / worst : {m.best_r:+.2f}R / {m.worst_r:+.2f}R",
    ]
    by_outcome: dict[str, int] = {}
    for t in r.trades:
        by_outcome[t.outcome] = by_outcome.get(t.outcome, 0) + 1
    if by_outcome:
        lines.append("  Outcomes     : " +
                     "  ".join(f"{k}={v}" for k, v in sorted(by_outcome.items())))
    return "\n".join(lines)


def main() -> None:
    args = sys.argv[1:]
    target = args[0] if args else "XAUUSD"
    tf = args[1] if len(args) > 1 else "H1"
    bars = int(args[2]) if len(args) > 2 else 700

    symbols = (list(config.load("symbols")["symbols"])
               if target.lower() == "all" else [target.upper()])
    src = YahooSource()
    bt = Backtester()

    all_r: list[float] = []
    for sym in symbols:
        try:
            df = src.fetch(sym, tf, bars)
        except Exception as exc:
            print(f"{sym}: skip — {str(exc)[:60]}")
            continue
        report = bt.run(sym, df)
        all_r += [t.result_r for t in report.trades]
        print(_report_text(report))
        print()

    if len(symbols) > 1 and all_r:
        from .metrics import compute_metrics
        agg = compute_metrics(all_r)
        print("═══════════ PORTFOLIO (all symbols) ═══════════")
        print(f"  Trades {agg.trades} · Win {agg.win_rate}% · Net {agg.net_r:+.2f}R · "
              f"PF {agg.profit_factor} · MaxDD {agg.max_drawdown_r:.2f}R · "
              f"Expectancy {agg.expectancy:+.3f}R")


if __name__ == "__main__":
    main()

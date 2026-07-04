"""Backtest performance & risk metrics (SRS doc 20 §9–10).

Pure functions over a list of per-trade results measured in R (risk multiples),
so every metric is deterministic and unit-tested without any market data.
"""
from __future__ import annotations

from pydantic import BaseModel


class Metrics(BaseModel):
    trades: int
    wins: int
    losses: int
    win_rate: float                  # %
    net_r: float                     # sum of per-trade R
    expectancy: float                # mean R per trade
    profit_factor: float             # gross win R / gross loss R (inf → 999.0)
    avg_win_r: float
    avg_loss_r: float
    max_drawdown_r: float            # deepest peak-to-trough on the cumulative R curve
    best_r: float
    worst_r: float
    sharpe: float                    # mean/std of per-trade R (0 if <2 trades)


def _max_drawdown(cum: list[float]) -> float:
    peak = 0.0
    dd = 0.0
    for x in cum:
        peak = max(peak, x)
        dd = min(dd, x - peak)
    return round(dd, 3)


def compute_metrics(results_r: list[float]) -> Metrics:
    n = len(results_r)
    if n == 0:
        return Metrics(trades=0, wins=0, losses=0, win_rate=0, net_r=0, expectancy=0,
                       profit_factor=0, avg_win_r=0, avg_loss_r=0, max_drawdown_r=0,
                       best_r=0, worst_r=0, sharpe=0)
    wins = [r for r in results_r if r > 0]
    losses = [r for r in results_r if r < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    net = sum(results_r)
    mean = net / n

    if n >= 2:
        var = sum((r - mean) ** 2 for r in results_r) / (n - 1)
        std = var ** 0.5
        sharpe = round(mean / std, 3) if std > 0 else 0.0
    else:
        sharpe = 0.0

    cum, running = [], 0.0
    for r in results_r:
        running += r
        cum.append(running)

    return Metrics(
        trades=n,
        wins=len(wins),
        losses=len(losses),
        win_rate=round(100 * len(wins) / n, 1),
        net_r=round(net, 3),
        expectancy=round(mean, 3),
        profit_factor=round(gross_win / gross_loss, 3) if gross_loss > 0 else 999.0,
        avg_win_r=round(gross_win / len(wins), 3) if wins else 0.0,
        avg_loss_r=round(sum(losses) / len(losses), 3) if losses else 0.0,
        max_drawdown_r=_max_drawdown(cum),
        best_r=round(max(results_r), 3),
        worst_r=round(min(results_r), 3),
        sharpe=sharpe,
    )

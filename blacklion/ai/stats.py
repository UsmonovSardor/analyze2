"""Expectancy stats engine (SRS docs 16-17, first feedback loop).

Rolling per-bucket statistics straight from the journal — n, win-rate, average
R (= expectancy per trade) and the share of losers that rode to the FULL −1R
stop (P4's success metric). Fully explainable: no model, just arithmetic.

The auto-throttle is the first "the bot learns from every closed trade"
mechanism: a strategy bucket with PROVEN negative expectancy (n ≥ min_n) is
publish-blocked — its signals keep being journaled (evidence keeps accruing,
and it can earn its way back) but the group stops seeing them.
"""
from __future__ import annotations

from ..core.logging import get_logger

log = get_logger("ai.stats")

# statuses whose R is realized profit-side vs loss-side
_WIN = {"tp1", "tp2", "tp3", "trailed"}


def bucket_stats(rows: list[dict], key: str = "strategy_name") -> dict[str, dict]:
    """Per-bucket {n, wins, win_rate, avg_r, full_stop_share} from
    Journal.closed_rows(). `key` may be strategy_name / symbol / timeframe."""
    out: dict[str, dict] = {}
    for r in rows:
        b = out.setdefault(str(r.get(key) or "?"),
                           {"n": 0, "wins": 0, "sum_r": 0.0,
                            "losses": 0, "full_stops": 0})
        rr = float(r["result_r"])
        b["n"] += 1
        b["sum_r"] += rr
        if rr > 0:
            b["wins"] += 1
        elif rr < 0:
            b["losses"] += 1
            if r["status"] == "stopped":
                b["full_stops"] += 1
    for b in out.values():
        b["win_rate"] = round(b["wins"] / b["n"], 3) if b["n"] else 0.0
        b["avg_r"] = round(b["sum_r"] / b["n"], 3) if b["n"] else 0.0
        b["full_stop_share"] = (round(b["full_stops"] / b["losses"], 3)
                                if b["losses"] else 0.0)
    return out


def portfolio_metrics(rows: list[dict]) -> dict:
    """Institutional performance metrics in R units (TITAN Bible 6.16 / 27).
    Money-agnostic — demo balances lie, R doesn't. Empty-safe."""
    rs = [float(r["result_r"]) for r in rows if r.get("result_r") is not None]
    if not rs:
        return {"n": 0, "total_r": 0.0, "win_rate": 0.0, "expectancy": 0.0,
                "profit_factor": 0.0, "sharpe": 0.0, "max_drawdown": 0.0,
                "recovery_factor": 0.0, "kelly_pct": 0.0}
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    total = sum(rs)

    # Kelly fraction (TITAN Bible 26.10): f* = W − (1−W)/RR, using realized
    # average win/loss. INFORMATIONAL only — not applied to sizing (Kelly on a
    # small, unproven sample over-leverages; kept as a discipline signal).
    win_rate_k = len(wins) / len(rs)
    avg_win = gross_win / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    payoff = avg_win / avg_loss if avg_loss else 0.0
    kelly = (win_rate_k - (1 - win_rate_k) / payoff) if payoff else 0.0
    mean = total / len(rs)
    var = sum((r - mean) ** 2 for r in rs) / len(rs)
    std = var ** 0.5

    # equity curve + max drawdown (in R)
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)

    return {
        "n": len(rs),
        "total_r": round(total, 2),
        "win_rate": round(len(wins) / len(rs), 3),
        "expectancy": round(mean, 3),                       # avg R per trade
        # ∞ profit factor (no losses yet) reported as gross_win for readability
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else
                         round(gross_win, 2),
        "sharpe": round(mean / std, 2) if std else 0.0,     # per-trade Sharpe
        "max_drawdown": round(max_dd, 2),
        "recovery_factor": round(total / max_dd, 2) if max_dd else round(total, 2),
        "kelly_pct": round(max(0.0, kelly) * 100, 1),   # capped at 0 (never negative)
    }


def throttled_strategies(rows: list[dict], min_n: int = 30) -> set[str]:
    """Strategy names with statistically-backed NEGATIVE expectancy — the
    runtime publish-blocks these (journal-only) until they recover. min_n
    guards against throttling on noise; do not lower it to "react faster",
    that is the overfitting trap."""
    stats = bucket_stats(rows, "strategy_name")
    bad = {name for name, s in stats.items()
           if s["n"] >= min_n and s["avg_r"] < 0}
    if bad:
        log.info("StrategiesThrottled", strategies=sorted(bad))
    return bad


def stats_report(rows: list[dict]) -> str:
    """Human-readable Uzbek block for the daily digest / /stats command."""
    stats = bucket_stats(rows, "strategy_name")
    if not stats:
        return "📊 Hali yopilgan savdolar yo'q."
    lines = ["📊 <b>Strategiya statistikasi</b> (yopilganlar):"]
    for name, s in sorted(stats.items(), key=lambda kv: -kv[1]["n"]):
        lines.append(
            f"  • {name}: n={s['n']} · win {s['win_rate'] * 100:.0f}% · "
            f"o'rtacha {s['avg_r']:+.2f}R · to'liq stop {s['full_stop_share'] * 100:.0f}%")
    return "\n".join(lines)

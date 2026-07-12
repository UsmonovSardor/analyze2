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

# Risk Rules

## Direction note (long vs short)

All rules below are written for LONGS. For a SHORT, mirror everything:
- R = stop_loss − entry  (stop is ABOVE entry).
- TP1 = entry − 1.5R, TP2 = entry − 2.5R, TP3 = entry − 4R (or nearest 4h SUPPORT, the closer one).
- SL goes ABOVE the structural invalidation (bounce swing high / reclaimed level).
- Ordering: stop_loss > entry > tp1 > tp2 > tp3.
- "Resistance above" becomes "support below" when checking for room.

## Stop-Loss Placement (structure-based, from Brooks + Nison)

- Place SL below the structural invalidation point:
  - **Setup A**: below the swing low of the pullback (the lowest point of the dip to EMA50).
    If a hammer formed, place SL just below the hammer's lower shadow tip.
  - **Setup B**: below the broken range high / retest low (the level that was just reclaimed).

- SL distance must be between **0.8× and 2.0× ATR(14, 1h)** from entry:
  - Closer than 0.8×ATR → noise will hit it → widen to nearest structure or reject.
  - Wider than 2.0×ATR → setup is too loose (excessive risk) → reject.

- **Never place SL inside the real body of a confirming candle** (Nison principle):
  If a morning star formed, the SL belongs below the FIRST bar of the morning star (the long black bar), not below the middle bar.

- After TP1 hits: **move SL to breakeven (entry price)**. State this explicitly in the signal.

---

## Take-Profits (R = entry − SL distance)

| Level | Calculation | Position size | Logic |
|-------|------------|---------------|-------|
| TP1 | entry + 1.5R | Take 40% | First partial — guarantees the trade is profitable |
| TP2 | entry + 2.5R | Take 40% | Core profit target — this is the minimum R:R gate |
| TP3 | entry + 4R OR nearest major 4h resistance (CLOSER one) | Final 20% | Let winners run — Paul Tudor Jones 5:1 philosophy |

Rules:
- If a major resistance sits **below 1.5R** from entry → the trade fails minimum R:R → **reject**.
- If a major resistance sits between 1.5R and 2.5R → set TP2 AT that resistance, not beyond it → verify R:R still ≥ 2.0 for TP2.
- TP3 should never be placed beyond a major 4h resistance — use the resistance as the TP3 cap.

---

## Risk:Reward Gate

- **Entry → TP2 must be ≥ 2.0R** (code enforces this). No exception.
- Ideal: Entry → TP2 ≥ 2.5R (cleaner trades tend to have more room).
- TP3 at 4R = the Paul Tudor Jones principle: "I am not going to risk a dollar to make a dollar."

---

## Position Sizing Guidance (informational)

- Risk per trade: **1% of account**.
- Position size = (account × 0.01) / (entry − SL).
- Hard cap: no single position exceeds **$100 USDT** on the live trading module.
- Daily loss stop: **−3R realized**. If this level is hit, no more trades for the day.

---

## Staleness Guard

- Entry must be within **±1.5% of current market price** (code enforces this).
- If the setup triggered more than 2×ATR ago, the analysis is stale → **reject**.

---

## Key Risk Principles from Market Wizards

"The most important common denominator among all the top traders I interviewed: **risk control above everything**." — Jack Schwager

- **Ed Seykota**: "Cut your losses. Let your profits run. The rest is noise."
- **Paul Tudor Jones**: "Don't focus on making money; focus on protecting what you have."
- **Michael Marcus** (turned $30k → $80M): "The risk control was the turning point. I never again allowed myself to lose everything on a single trade."
- **Lesson for our system**: The stop-loss is not a formality. It is the PRIMARY decision. Determine the stop FIRST. Only then check if the R:R is acceptable.

---

## Confidence Score

- Report confidence as the confluence score (0–10). Signals below 6 are never emitted.
- Score 6 = acceptable (lower conviction). Score 8+ = preferred. Score 9–10 = high-conviction.
- When recent setup performance (fed back via performance note) shows win rate < 40% for this setup type: raise minimum score to 8.

# Strategy Rules — Spot Swing (1h entry / 4h context)

Only TWO setups are tradeable. Anything else is `none`.

---

## Setup A — Trend Pullback (High 2 / EMA50 Retest)

**Source**: Nison candlestick reversal + Brooks High-2 pullback + Livermore trend following

Context (4h), ALL required:
- Price above EMA200 AND EMA50 above EMA200 (confirmed uptrend)
- Structure of higher highs and higher lows
- BTC 4h is not in a strong downtrend

Entry conditions (1h), ALL required:
1. **Pullback depth**: Price pulled back to the EMA50 zone (±1.0×ATR) OR to a prior breakout level / swing support — must be within 25%–75% retracement of the prior bull swing. If > 75%: reject.
2. **RSI reset**: RSI(14) dipped below 45 at some point in the last 6 bars, AND current RSI > prior bar's RSI (turning up). RSI reset below 40 = stronger signal.
3. **Candle confirmation** (from Nison): At least ONE of these on the signal bar (bar closing at/after the pullback):
   - Hammer (lower shadow ≥ 2× body)
   - Bullish engulfing (bull bar engulfs prior bear bar)
   - Morning star (3-bar pattern)
   - Piercing pattern (closes above 50% of prior bear bar)
   - "ii" inside-inside pattern with bull breakout bar
   - Strong bull trend bar (body ≥ 60% of range, closes top 25%)
4. **Pullback volume**: Pullback bars (bear bars in the dip) should have LOWER volume than the prior impulse leg average. Healthy retracement = low-volume dip. High-volume selling into support = red flag.
5. **No large upper wick on signal bar**: If the entry bar has an upper wick > 60% of its total range, the bears are absorbing buyers. Reject.

**High-quality bonus** (add to reasoning):
- Two-legged pullback (leg 1 then leg 2 = "Higher 2" / "High 2" per Brooks): signal is much stronger than a single-leg dip
- Sell climax before the pullback (15+ red bars, RSI < 25, then hammer): extremely high quality
- The midpoint of a prior long white candle (Nison) coincides with the EMA50 — double support

---

## Setup B — Range Breakout with Retest

**Source**: Brooks breakout analysis + Nison long white candle breakout confirmation

Context (4h), ALL required:
- Price was compressed in a range for ≥ 30 bars (1h) with a clearly defined upper boundary
- BTC 4h is not in a strong downtrend

Entry conditions (1h), ALL required:
1. **Close above range high** with volume ≥ 1.5× the 20-bar average ON THE BREAKOUT BAR.
2. **Entry method** (choose the BETTER one):
   - **Preferred (retest)**: After the breakout, price pulls back to the broken level. Enter on the close of a small bear bar or doji at that level — it must NOT close back below the range high. This is the highest-quality Setup B entry.
   - **Immediate breakout**: Enter within 0.5×ATR(14) of the breakout bar's close — only if the breakout bar is a strong bull trend bar (body ≥ 60% of range, no large upper wick).
3. **No higher-timeframe resistance within 1R of entry**: Check 4h resistance levels.
4. **Candle quality at entry** (Nison): The entry bar should be a strong bull trend bar or a small doji/inside bar at the retest level. A large upper wick at the retest = trap, reject.

**Failed breakout warning** (Brooks "bull trap"):
- Breakout bar is large but next bar REVERSES most of it (closes below the range high).
- This is a bull trap. Do NOT enter. Institutional sellers absorbed the breakout buyers.
- If you already entered, this is an early exit signal.

---

## Market Regime (MUST determine BEFORE scoring)

**Regime 1 — Strong Bull Trend**: 4h EMA50/200 aligned, price well above both, clean higher high/higher low structure. → Setup A is the primary setup. Setup B allowed.

**Regime 2 — Bull Trend with Pullbacks**: Bull trend but price has corrected significantly. EMA50 being tested on 4h. → Setup A only. Extra candle confirmation required.

**Regime 3 — Range / Consolidation**: Flat or narrowing EMAs, price oscillating between defined levels. → Setup B ONLY on confirmed breakout. Buying mid-range is FORBIDDEN (Reminiscences: "don't guess the breakout direction, wait for the market to tell you").

**Regime 4 — High-Volatility Chop**: Huge wicks, ATR spiking > 2× normal, no structure, EMAs tangled. → **NOTHING IS ALLOWED. Reject everything.** (Livermore: "There are times when I won't do anything. Not even consider a trade.")

**Regime 5 — Bear Trend / Downtrend**: Price below EMA200, EMA50 < EMA200. → **Hard reject all longs. Look for SHORT setups (A or B short) instead**, trading WITH the down-trend. (Nison: "place a new position based on a reversal signal ONLY if that signal is in the direction of the major trend.")

---

## Short Setups (mirror image — only in a 4h DOWNTREND)

Both setups apply symmetrically to the short side. Everything flips:

- **Setup A short (bounce to EMA50 in a downtrend)**: 4h price below EMA200 and EMA50 < EMA200.
  Price bounces UP into the EMA50 zone (±1.0×ATR) or a prior breakdown level. RSI rallies toward
  55–65 then turns DOWN. Entry on a bearish confirmation candle (shooting star, bearish engulfing,
  evening star, strong bear trend bar). SL ABOVE the bounce swing high. Targets below.
- **Setup B short (range breakdown + retest)**: price breaks BELOW a ≥30-bar range low on volume
  ≥ 1.5× average, then retests the broken level from below. Enter on a small bull bar / doji that
  fails to reclaim the level. SL above the broken level. A failed breakdown (price reclaims the range
  low) is a bull trap against you — do NOT enter.

For shorts, "BTC context" means BTC 4h should be neutral-to-bearish (don't short alts into a strong
BTC bull). All other rejection rules apply with direction reversed.

---

## Confluence Scorecard (need ≥ 6 to pass)

Score maps 1:1 to the `scorecard` object in `signal-format.md`. Maximum 10 points.

| # | Factor (scorecard key) | Points | How to judge |
|---|--------|--------|--------------|
| 1 | **4h trend aligned** (`trend`) — EMA50 > EMA200, price above both | 2 | Both required for 2 pts; price above EMA200 only = 1 pt; neither = 0 |
| 2 | **Entry at a real level** (`level`) — EMA50, prior breakout, swing S/R, 4h pivot, FVG, order block | 2 | Two or more levels coincide = 2 pts; single clear level = 1 pt; vague zone = 0 pts |
| 3 | **Volume confirms** (`volume`) — pullback volume < impulse avg, OR entry/breakout bar volume ≥ 1.2× avg | 2 | Both/clear = 2 pts; one = 1 pt; volume against = 0 pts |
| 4 | **RSI/MACD momentum aligned** (`rsi`) — RSI reset below 45 + turning in trade direction | 1 | RSI divergence AGAINST the trade = 0 pts here |
| 5 | **BTC / macro context supportive** (`btc`) — BTC 4h bullish/neutral for longs; bearish for shorts | 1 | BTC actively falling on 4h during a long = 0 pts |
| 6 | **Clean room to TP2** (`room`) — nearest resistance ≥ 2R away from entry | 1 | Major resistance < 1R = reject entire trade; 1–2R = 0 pts here but trade allowed |
| 7 | **Candle confirmed** (`candle`) — hammer/engulfing/morning star/strong trend bar at entry level | 1 | Weak or absent pattern = 0 pts |

**Maximum score: 10 points. Minimum to signal: 6 points.**
Score every factor explicitly and state the exact points. Extra confluence beyond the scorecard
(ICT smart-money, Brooks two-leg structure, multiple strategy families agreeing) does not add raw
points but should push a borderline 6 toward a confident signal — mention it in the reasoning.
For shorts, score each factor as its mirror (trend DOWN, RSI rolling over, breakdown volume, etc.).

**From Market Wizards**: "Risk control is the #1 common denominator among ALL top traders." A setup
that scores 6 and passes the rules is a valid signal — do not negotiate the minimum upward without cause.

---

## Hard Rejection Rules

- BTC 4h trend is strongly down (EMA50 < EMA200 AND price below both) AND candidate is an altcoin → **reject** (alts follow BTC).
- Price is mid-range with no nearby support → **reject** (buying mid-range is forbidden per Brooks and Livermore).
- The move already extended > 2×ATR(14) from the trigger level → too late, momentum gone → **reject**.
- Volume does NOT confirm (breakout on below-average volume, or pullback on HIGHER volume than the impulse) → **reject** (bears are selling aggressively).
- Bearish candle pattern present at entry zone (shooting star, dark cloud cover, evening star, bearish engulfing) → **reject** (Nison: "bearish signals require defensive action").
- Pullback > 75% of prior bull swing → likely trend failure → **reject** (Brooks 75% rule).
- Large upper wick on signal bar (> 60% of total range is wick) → supply zone, distribution → **reject**.
- 4 or more tests of the same resistance level without a break → level is about to break but short-term risk too high → **reject**.
- Major 4h resistance sitting within 1R above entry → insufficient room → **reject**.

---

---

## ICT Smart Money Models (Advanced Setups — Setup C/D)

These models extend Setup A/B with ICT (Inner Circle Trader) Smart Money Concepts. Use them as additional confluence or as standalone setups when classic A/B conditions are absent.

---

### ICT AMD / Power of Three (PO3)

**Timeframe**: 5m (entries), 1h (context). Works on any session.

**Structure**: Market moves in 3 phases:
1. **Accumulation** — tight consolidation range (identify using candle BODIES, not wicks)
2. **Manipulation** — quick spike OUT of the range then BACK inside it (false breakout to grab liquidity)
3. **Distribution** — directional move to the opposite side of the accumulation range

**Entry Trigger #1 — iFVG Retest**: During the manipulation leg, a Fair Value Gap forms. When price inverts that FVG and retests it, enter.
- SL: at manipulation high (short) or low (long)
- TP: 2 standard deviations of the manipulation leg (if provides ≥2R), else 4 STDV

**Entry Trigger #2 — Box Setup**: No iFVG available. After price closes back into the accumulation zone, enter on retest of the manipulation box high (longs) or low (shorts).
- Same SL/TP as above

**Win rate boosters**:
- HTF liquidity swept during manipulation (session H/L, prior day H/L)
- Trade aligns with HTF AMD distribution direction
- Continuation trades only when HTF trend agrees

**AMD/PO3 Checklist**: Accumulation zone identified → Manipulation out-and-back confirmed → Entry on iFVG retest or manipulation box retest → SL at manipulation extreme → TP at 2 STDV (≥2R) or 4 STDV

---

### ICT Judas Swing (Asia Session Variation)

**Timeframe**: 5m. **Pairs**: GBPJPY (primary), GU, EU, AU. **Session**: London open 3:00–5:30am NY time.

**Asia Range**: 9am–4pm Tokyo (00:00–07:00 UTC). Mark the high and low of this range.

**Setup**:
1. Price sweeps the Asia H or Asia L during London session (creates a false break)
2. Wait for 5m market structure shift (MSS) — a candle that closes back inside the Asia range
3. Enter on MSS candle close. SL at the sweep high/low.
4. TP = opposite side of the Asia range. No active trade management.

**Invalidations** (do NOT trade if any apply):
- Sweep extended >50% OUTSIDE the Asia range (use Fib 0/1/-0.5 to measure)
- Longs: price must be in BOTTOM half of Asia range at time of entry
- Shorts: price must be in TOP half of Asia range at time of entry
- No trendline liquidity visible (prior swing highs/lows that form a trendline = required)

**Judas Swing Checklist**: Asia H/L marked → Sweep during London session (<50% deviation) → Trendline liquidity present → MSS on 5m (entry) → Entry at or below/above Asia midpoint → TP opposite side of Asia range

---

### ICT Unicorn Model

**Timeframe**: 5m. **Market**: ES/NQ (indices). **Session**: NY after 9:30am.

**Key concepts**:
- **Breaker** = failed order block. Bullish breaker: last green candle BEFORE a lower low. Bearish breaker: last red candle BEFORE a higher high.
- **FVG** = Fair Value Gap: non-overlapping wicks between 3 consecutive candles.
- **DOL** = Draw on Liquidity: equal highs (buy-side) or equal lows (sell-side).

**Steps**:
1. Identify DOL (equal highs or equal lows as the target)
2. Wait for manipulation AWAY from the DOL
3. Displacement back toward DOL forms an overlapping Breaker + FVG (Unicorn = both overlap)
4. Enter on retest of the Breaker/FVG overlap zone
5. SL: body high/low of the manipulation leg
6. TP: 2 STDV of manipulation leg OR hold to the DOL (whichever provides ≥2R)

**Rules**: No trades during red-folder news. Trade must provide ≥2R. No active management, let it play out.

**Unicorn Checklist**: DOL identified → Manipulation away from DOL → Overlapping Breaker + FVG formed → Retest of BB/FVG (entry) → SL at manipulation body H/L → TP 2 STDV or DOL

---

### ICT Venom Model (2025)

**Timeframe**: 1m. **Market**: NQ (primary), indices, gold. **Session**: 9:30–11:00am NY only.

**Setup**:
1. Mark the 8:00–9:30am NY pre-market range H/L
2. After 9:30am open, price takes out the 8-9:30am high OR low
3. An initial FVG forms on 1m

**Entry #1 — BPR Retest** (preferred): After the sweep, a Balanced Price Range (BPR = two overlapping FVGs) forms. Enter on limit order at BPR retest.
- SL: recent swing H/L
- TP: fixed 2R (or other side of 8-9:30am range with HTF bias)

**Entry #2 — Venom Breakout**: A strong engulfing candle inverts the initial FVG (closes past it). Enter market order.
- SL: open of the engulfing candle
- TP: fixed 2R

**Rules**:
- No trades after 11:00am NY
- No trades if price already hit 2R before BPR forms
- No trades near red-folder news
- 2nd attempt allowed if first entry stopped out and new entry forms

**Venom Checklist**: 8-9:30am range marked → 9:30am sweep of range H/L → Initial FVG noted → BPR retest (Entry #1) OR engulfing inverts FVG (Entry #2) → SL at swing H/L or candle open → TP 2R fixed

---

### ICT Turtle Soup (TBL Sweep + Reversal)

**Timeframe**: 5m. **Market**: NQ/ES. **Session**: NY after 9:30am.

**Core concept**: Time-Based Liquidity (TBL) — session H/L, previous day H/L (PDH/PDL), Asia H/L, London H/L. After TBL sweep, smart money reverses.

**Bias identification**: Use TBL levels, NWOGs (New Week Opening Gaps = gap between Friday close and Sunday open), and premium/discount array.

**Entry #1 — CISD Retest (Reversal)**: After TBL sweep, wait for CISD (Change in State of Delivery — candle that closes past the body of the recent price leg). Enter on CISD retest with SL at recent H/L. TP: internal H/L, FVG fill, or premium/discount rebalance. Target 1.5–2R.

**Entry #2 — FVG Retest (Continuation)**: Clear DOL identified. Look for FVG to retest on the way to DOL. SL at H/L of candle that formed the FVG. Fixed 2R TP.

**Rules**:
- Ignore doji/small-bodied candles for CISD signals
- Cancel limit orders if TP hit before entry
- Don't take continuation trades near opposing TBL (don't long when too close to buy-side TBL)
- Max 2 attempts per day (for beginners: done after 1 win)

**Turtle Soup Checklist (CISD)**: TBL sweep → Reversal bias → CISD candle formed → Limit entry on CISD retest → SL at recent H/L → TP 1.5–2R

**Turtle Soup Checklist (FVG)**: DOL identified → Reversal started → FVG retest (entry) → SL at FVG candle H/L → Fixed 2R TP

---

### ICT MMXM (Market Maker Buy/Sell Model)

**Timeframe**: 1h for HTF POI identification, 5m for entries. **Market**: MES/MNQ (indices). **Session**: 9:30am–3:00pm ET.

**The full MMXM cycle**:
- **Market Maker Buy**: Original Consolidation → 1st Stage Distribution (down) → 2nd Stage Distribution (lower) → 1st Stage Accumulation → 2nd Stage Accumulation → Smart Money Reversal → Buy side of curve (up)
- **Market Maker Sell**: Mirror image upward then down

**Daily Bias**: Use 1h 200 EMA. Price above = bullish bias, below = bearish.

**HTF POI** (Points of Interest): 1h FVGs, Balanced Price Ranges (BPR), or Order Blocks (supply/demand zones).

**Smart Money Reversal (SMR)**: Occurs near HTF POI. Requires TWO forms of liquidity taken (HTF + LTF) + SMT Divergence (two correlated assets making divergent H/L, e.g., ES vs NQ).

**Three entry tiers**:

1. **Low-risk buy/sell** (highest R, lower win rate): LTF Breaker + FVG at HTF POI (= Unicorn Model entry). SL at local low/high. TP first opposing liquidity ≥2R.

2. **1st stage accumulation/distribution** (moderate R and win rate): Enter on Order Block retrace (Doyle Exchange model). After wick into OB, enter above (below) candle that wicked into OB. SL at wick low (high). TP first FVG fill or opposing liquidity ≥3R.

3. **2nd stage re-accumulation/re-distribution** (lower R, higher win rate): Same as 1st stage entry but TP = original consolidation liquidity (external liquidity).

**MMXM Rules**: No entry near red-folder news. No active trade management.

**MMXM Low-Risk Checklist**: MMXM model near HTF POI → LTF SMT Divergence during manipulation → Market Structure Shift + overlapping Breaker + FVG → Retest of FVG/Breaker (Unicorn entry) → TP first opposing liquidity ≥2R

---

## ICT Concept Glossary (for AI signal reasoning)

| Term | Definition |
|------|-----------|
| FVG | Fair Value Gap: 3-candle pattern where candle 1 wick and candle 3 wick do NOT overlap |
| iFVG | Inverse FVG: an FVG that price has traded through and now acts as support/resistance |
| BPR | Balanced Price Range: two overlapping FVGs |
| Breaker | Failed order block: last green before LL (bullish) or last red before HH (bearish) |
| CISD | Change in State of Delivery: candle closing past the body of the prior price leg |
| DOL | Draw on Liquidity: target (equal highs = BSL, equal lows = SSL) |
| TBL | Time-Based Liquidity: session/day/week H/L levels |
| NWOG | New Week Opening Gap: gap between Friday close and Sunday open |
| SMT | Smart Money Tool/Divergence: two correlated assets making divergent extremes |
| MSS | Market Structure Shift: first candle that breaks prior swing high/low |
| HTF POI | Higher Timeframe Point of Interest: FVG/OB/BPR on 1h or higher |
| BSL/SSL | Buy-Side Liquidity / Sell-Side Liquidity (stop clusters above highs / below lows) |
| PDH/PDL | Prior Day High / Prior Day Low (key TBL levels) |

---

## Additional Strategy Models

### Matt's Wicks Setup

**Timeframe**: 1h (HTF context) → LTF entry. **Market**: Any. **Session**: London / NY.

**Setup**:
1. Identify HTF Level + Major Liquidity Pool (equal highs/lows, swing point)
2. Wait for a clean impulsive leg into that HTF level
3. On LTF: look for M/W Formation (double top/bottom pattern)
4. Require SMT Divergence between correlated pairs (e.g. EU vs GU)
5. Wait for Change in State (CSD) — candle closes past body of prior leg
6. FVG forms in the CSD move → entry on FVG retest

**Entry**: Limit at FVG. SL: below structural invalidation (swing low for longs, swing high for shorts).
**TP**: Major opposing liquidity pool. No fixed R — size the stop to the structure.

**Checklist**: HTF level + liquidity pool → clean impulsive leg → M/W formation → SMT divergence → CSD candle → FVG retest entry → SL below structural invalidation

---

### Ali Khan Dealing Range Theory (DRT)

**Timeframe**: 1h context, 5m entry. **Market**: EURUSD, GBPUSD. **Session**: London / NY.

**Core concept**: Dealing Range = the H/L formed after a liquidity sweep + rebalance. Draw Fibonacci 0/0.25/0.5/0.75/1 over this range — these become "DRT quadrants" (orange lines at 25%/75%, midpoint at 50%).

**Entry Trigger 1 — Quadrant Break**: 5m candle closes through the 25% or 75% DRT level.
- Limit order at the broken level (orange line)
- SL: at the range H or L (beyond the quadrant)
- TP: opposite side of range (full DRT target)
- Min 3:1 R:R

**Entry Trigger 2 — Midpoint Sweep**: 5m candle closes through the 50% DRT level.
- Limit at 50% DRT
- SL: one quadrant beyond entry (25% distance)
- TP: relative equal H/L (liquidity at range boundary)
- Min 2:1 R:R

**Rules**: Only trade during London / NY. No trade if DRT not clearly defined (need sweep + rebalance to mark the range). Cancel limit if TP hit before entry fills.

**Checklist**: Sweep + rebalance defines DRT → fib 0/0.25/0.5/0.75/1 drawn → 5m close through 25/75 (Trigger 1) or 50 (Trigger 2) → limit entry at broken level → SL at range boundary → TP opposite side or rel. equal H/L

---

### Fibonacci Retracement Forex Swing

**Timeframe**: 4h. **Market**: Forex (major pairs). **Session**: Any.

**Setup**:
1. 200 EMA + 50 EMA both on chart
2. Identify clear swing structure using fractals
3. Draw Fibonacci from swing low to swing high (longs) or high to low (shorts): levels 0 / 0.71 / 1
4. 0.71 fib must align with the 50 EMA tap (or very close)

**Entry**: Wait for a reversal candle that closes back on the correct side of both the EMA and the 0.71 fib level.
**SL**: Recent swing H/L (minimum 10 pips distance). Reject if SL < 10 pips.
**TP**: 2R fixed.

**Checklist**: 4h chart → 200+50 EMA + fractals → fib 0/0.71/1 drawn → 0.71 aligns with EMA → reversal candle close back above/below EMA + 0.71 → SL at recent H/L (min 10 pips) → TP 2R

---

### Quarterly Theory + SMT (SSMT)

**Timeframe**: 5m (90-minute quarters). **Market**: EURUSD/GBPUSD (London), ES/NQ (NY). **Session**: London 2–9am ET, NY 9:30–15:30 ET.

**Core concept**: Each session divides into 90-minute quarters. SSMT (Session SMT) = divergence between two consecutive 90-minute quarters — one makes a higher high while the other makes a lower high (or vice versa), signaling manipulation.

**Entry**:
- Identify SSMT between consecutive 90m quarters (crack in correlation between EU/GU or ES/NQ)
- Enter on PSP (Price Swing Point — a clear H or L in the SSMT zone) or engulfing candle on the stronger/weaker of the two pairs
- Direction: trade the pair that "won" the SMT (the one that didn't make the false extreme)

**SL**: Recent H/L of the entry candle (minimum 5 pips for forex).
**TP**: 3R fixed.

**Checklist**: Identify 90m quarters → SSMT divergence between consecutive quarters → PSP or engulfing entry → SL recent H/L (min 5 pips) → TP 3R

---

### Opening Range Break (ORB)

**Timeframe**: 5m (NY) or 5m (London). **Market**: Any (indices, forex, stocks).

**NY ORB**: Range = 9:30–9:45am (15 min). **London ORB**: Range = 3:00–3:30am ET (30 min).

**Entry Trigger 1 — Market Order**: 5m candle closes outside the ORB range H or L. Enter market order immediately.
- SL: midpoint of the ORB range
- TP: 1 Standard Deviation extension beyond the ORB (mark with StdDev tool)

**Entry Trigger 2 — Retest**: If the range is too large for Trigger 1, wait for a retest of the broken ORB H or L after initial breakout.
- Limit order at the ORB level
- Same SL/TP as Trigger 1

**Rules**:
- Max 2 losses per day; done for the day after 1 win
- No trades during red folder news events

**Checklist**: Mark 9:30–9:45am (NY) or 3–3:30am ET (London) range H/L → 5m close outside range (Trigger 1) or retest after break (Trigger 2) → SL at midpoint → TP 1 StdDev → max 2 losses/day, done after 1 win

---

### Doyle Exchange Supply & Demand

**Timeframe**: 5m. **Market**: GBPJPY. **Session**: London.

**Zone Identification**:
- **Supply zone**: Last GREEN candle (Order Block) immediately before a strong impulsive move DOWN
- **Demand zone**: Last RED candle (Order Block) immediately before a strong impulsive move UP
- Trend filter: 200 EMA — only long if above EMA, only short if below EMA

**Entry**: Price must WICK into zone (candle body does not close inside zone). Place buy/sell stop just beyond the wick extreme.
**TP**: 3R minimum. Move to break-even at 1R.

**Rules**:
- Zone invalidated if price closes a candle body inside it
- No trade if EMA direction contradicts the setup

**Checklist**: 200 EMA trend direction → identify last OB before impulsive leg → price wicks into zone (no close) → buy/sell stop entry → TP 3R+, b/e at 1R

---

### Bernd's Globex Trap Strategy

**Timeframe**: 5m. **Market**: ES, NQ, DOW, Russell (indices). **Session**: NY open (first 30–60 min after 9:30am ET).

**Core concept**: Globex H/L = the range formed during ETH (extended trading hours, 6pm–9:30am ET). Supply/Demand zones within the Globex range follow a specific structure:
- **Supply**: RBD (Red-Base-Drop) or DBD (Drop-Base-Drop) — base must have <6 candles, departure must be explosive
- **Demand**: DBR (Drop-Base-Rally) or RBR (Red-Base-Rally) — same rules

**Entry**: After Globex Low is swept (for longs), enter limit order at identified demand zone within the Globex range.
- SL: 33% past the zone boundary
- **HTF Aligned (trend with Globex direction)**: TP 4R, move to b/e at 2R
- **Counter-HTF**: TP 2R, move to b/e at 1R

**Checklist**: Mark Globex H/L (6pm–9:30am) → identify supply/demand zones (RBD/DBD for supply, DBR/RBR for demand, <6 candles, explosive departure) → Globex Low/High swept → limit at zone → SL 33% past zone → HTF aligned: TP 4R b/e at 2R; counter: TP 2R b/e at 1R

---

### Trader Mayne Monday Range

**Timeframe**: 1h + Daily. **Market**: BTC, ETH, crypto. **Session**: NY / Asia.

**Core concept**: Mark Monday's H/L range every week. Two trade triggers based on how price interacts with Monday range.

**Trigger 1 — Range Reclaim**: Price closes past Monday H or L (breakout), then closes BACK INSIDE the range.
- Market entry on the close back inside
- SL: recent H/L (beyond the breakout candle)
- TP: opposite side of Monday range
- Move to b/e at Monday range midpoint
- Min 2R required

**Trigger 2 — Monday Open Sweep**: Price sweeps the weekly open (wick through it is ok), then closes back over/under the weekly open.
- Market entry on the close back over/under
- SL: recent H/L
- Min 2R required

**Rules**: No trades on Friday or Saturday. Both triggers require min 2R to the TP target before entry.

**Checklist**: Mark Monday H/L and weekly open → Trigger 1: close outside range, then close back inside (market entry) OR Trigger 2: wick through weekly open, close back over it → SL recent H/L → TP opposite side of range → b/e at midpoint → min 2R → no Fri/Sat

---

### Tori Trades Trend Line (Swing)

**Timeframe**: 4h. **Market**: Platinum, Crude Oil, Gold, DOW. **Session**: Any.

**A+ Trend Line criteria**:
1. At least 3 touches
2. At least 6 candles between each touch
3. Angle less than 45 degrees
4. Trend line must be at least 3 weeks old

**Entry**: 4h candle closes PAST the trend line (break). Enter on the close of that candle.
**SL**: Where the 4th candle after the break touches the "safety line" (a parallel reference line drawn below/above the trend line). Wait for candle 4 to form, then place SL there.
**TP**: First S/R zone at minimum 2R distance. Only take if TP ≥ 2R.

**Rules**: One attempt per trend line (no re-entry after SL). If TP < 2R from entry, skip the trade.

**Checklist**: A+ trend line (3+ taps, 6+ candles between, <45°, 3+ weeks old) → 4h close past trend line → SL where 4th candle hits safety line → TP first S/R zone ≥ 2R → one attempt only

---

### SMB Capital Offsides Scalping

**Timeframe**: 5m. **Market**: YM (DOW futures). **Session**: 5am–12pm NY only.

**Indicators**: VWAP + Volume.

**Trigger 1 — Offsides Reversal**: Price deviates significantly from VWAP AND volume shows divergence (price making new extreme on lower volume than previous).
- Stop-limit entry (trigger when price starts to reverse)
- SL: midpoint between entry and the H/L of the deviation
- TP: 2R

**Trigger 2 — VWAP Flip**: A decisive candle (strong body, minimal wick) flips price from one side of VWAP to the other.
- Market order entry on the flip close
- SL: recent H/L before the flip candle
- TP: 1R

**Rules**:
- No trades during red folder news events
- No trades at NY open (9:30am) — wait 10–15 minutes
- Session ends at 12pm NY

**Checklist**: 5am–12pm NY window → VWAP visible on chart → Trigger 1: price deviation + volume divergence (stop-limit, SL midpoint, TP 2R) OR Trigger 2: decisive VWAP flip candle (market entry, SL recent H/L, TP 1R) → no news, no 9:30am entry

---

### Jooviers Gems Hybrid Superscalp

**Timeframe**: 1m. **Market**: NQ (primary). **Session**: 8am–3pm NY.

**Indicators**: 100 EMA + Heikin Ashi candles.

**Setup (Long)**: Price is making higher lows above the 100 EMA. Need 2+ consecutive "clean" pullback candles (flat bottom / rounded bottom, near-doji shape) immediately followed by a high-volume doji candle.

**Setup (Short)**: Mirror — lower highs below 100 EMA. Same clean pullback + high-volume doji.

**Entry**: Market order on the break of the high-volume doji (for longs: buy above doji high; for shorts: sell below doji low).
**SL**: At the doji H or L (the doji's extreme in the opposite direction).
**TP**: 1R (measured as the same distance as the SL, placed as a limit order).

**Rules**: No red folder news. Clean pullback candles = candles with flat/equal bottoms (longs) or flat/equal tops (shorts) — no mixed wicks.

**Checklist**: 100 EMA trend → higher lows above EMA (long) or lower highs below EMA (short) → 2+ clean pullback candles → high-volume doji → market entry → SL at doji extreme → TP 1R

---

### Scarface Trades 5m ORB Scalp

**Timeframe**: 1m execution, 5m reference. **Market**: Tesla, NVIDIA, Apple, AMD (stocks). **Session**: NY 9:30–11:00am only.

**Setup**:
1. Mark the 5m H and L of the first 5m candle after market open (9:30am)
2. Wait for price to break out of this range
3. Retest: price must come back to retest the range H/L — or the FVG formed during the breakout move
4. There must be visible price space (gap) BEFORE the retest candle (no immediate reversal)
5. Entry candle confirmation required (candle closes in breakout direction after touch)

**Entry**: Market order on confirmation candle close.
**SL**: At the H or L of the retest candle (or the opposite side of the FVG retest zone).
**TP**: 2R minimum, or new H/L of the day (whichever comes first).

**Rules**: Max 2 attempts per day. Done after 1 win. No trades after 11am.

**Checklist**: Mark 9:30am 5m H/L → breakout (either direction) → visible gap before retest → price retests range H/L or FVG → confirmation candle closes in breakout direction → market entry → SL at retest H/L → TP 2R+ or day H/L → max 2 attempts, done after 1 win

---

### Omar Agag EBP (Engulfing Bar Play) Swing

**Timeframe**: 4h+. **Market**: XAUUSD, EURUSD, NQ. **Session**: Any.

**EBP definition**: A candle that sweeps BOTH the previous candle's high AND low (wick past both extremes), then closes beyond the BODY of the previous candle (not just the wick).

**Fibonacci measurement** (draw 0→1 over the EBP candle, 0 at start, 1 at the end of the close):
- Levels: 0 / 0.15 / 0.25 / 0.5 / 0.75 / 1

**Trigger 1 — Strong EBP** (candle close within 15% of its extreme, i.e. close ≤ 15% from the H or L):
- Limit order at 25% retrace of the EBP candle
- SL: at 75% retrace
- TP: 2R fixed

**Trigger 2 — Indecisive EBP** (candle close > 15% from the extreme):
- Limit order at 50% retrace
- SL: at origin of the EBP candle (the 1.0 level)
- TP: 2R fixed

**Trade management**: Move to break-even after price forms a new HH (for longs) or new LL (for shorts).

**Checklist**: 4h+ EBP candle (sweeps both H/L, closes past body) → measure fib 0–1 → close ≤15%: limit at 25%, SL at 75% (Trigger 1) OR close >15%: limit at 50%, SL at origin (Trigger 2) → TP 2R → b/e after new HH/LL

---

### Tomtrades CBR (Candle Behavior Reversal) Simplified

**Timeframe**: 1m. **Market**: XAUUSD. **Session**: 2nd hour of Asia (0:00 UTC, i.e. midnight UTC).

**Bias determination**: Check 1h Gold vs DXY correlation. Gold and DXY move opposite — if DXY is bullish, gold bias is bearish (and vice versa). Opposing moves add confluence.

**Setup steps**:
1. Wait for 20+ minute expansion without significant pullbacks (strong impulse)
2. In the 1st hour of Asia: price sweeps a key level OR rebalances a range
3. Wait for a 30m candle to sweep the session H or L
4. Look for a "Type 3 Shift" (MSB after local structure is taken out): a candle that closes past the prior swing high (for longs) establishing a new local structure break

**Entry**: Around the 50% pullback of the MSB move (after the Type 3 shift).
**SL**: At the H or L of the Type 3 shift candle.
**TP**: 50% equilibrium of the prior expansion OR 1.5R (whichever is closer).

**Checklist**: 1h Gold vs DXY direction → 20min+ expansion → 1st Asia hour sweep/rebalance → 30m candle sweeps session H/L → Type 3 shift (MSB after local structure taken) → entry at ~50% pullback of MSB → SL at Type 3 shift H/L → TP equilibrium or 1.5R

---

### Toto Capital SBL (Session-Based Liquidity) Reversal

**Timeframe**: 15m. **Market**: S&P 500, XAUUSD. **Session**: London 3–5am ET OR NY 8–10:30am ET.

**EMA Alignment filter**:
- Longs: 50 EMA > 100 EMA > 200 EMA (all stacked bullish)
- Shorts: 50 EMA < 100 EMA < 200 EMA (all stacked bearish)

**Entry Steps**:
1. Confirm EMA alignment (all 3 EMAs stacked in trend direction)
2. During the trade window, price sweeps a session-based liquidity level (equal highs/lows, prior session H/L) IN LINE with the trend direction
3. After the sweep, the next 15m candle closes back IN the trend direction
4. Place stop order on the break of that candle's H (for longs) or L (for shorts) — enter when price breaks that candle

**SL**: At the H or L of the sweep candle (the extreme of the liquidity sweep).
**TP**: 2R fixed. No active trade management.

**Checklist**: London 3–5am ET or NY 8–10:30am ET → 50/100/200 EMA stacked (longs: bull stack, shorts: bear stack) → session liquidity sweep in trend direction → 15m candle closes in trend direction → stop order on that candle's H/L break → SL at sweep extreme → TP 2R fixed

---

### Nvidia Anchored VWAP (AVWAP) Strategy

**Timeframe**: 30m context, 2m execution. **Market**: NVIDIA (NVDA), other individual stocks. **Session**: NY only.

**Indicators**: Standard VWAP (daily reset) + Anchored VWAP (AVWAP) drawing tool. Set AVWAPs from: most recent earnings candle, major swing high, major swing low, and significant breakout points.

**Entry Model**: Wait for price to retest an AVWAP level, then wait for a 2m Market Structure Break (MSB — candle close past prior swing H/L).
- Market entry on MSB
- SL: conservative = retest candle H/L; aggressive = most recent structural H/L before entry
- TP: 1.5R fixed, OR trail stop to previous day H/L, OR trail to opposing AVWAP level

**Rules**:
- Avoid trades when two AVWAPs are too close together (choppy zone between them)
- For intraday: close by market close if TP/SL hasn't hit
- No trade if new day H/L prints before your entry (missed move)
- Can take partial TP at 1.5R and trail runner with stop

**Checklist**: AVWAPs marked (earnings, swing H/L, breakouts) → price retests AVWAP → 2m MSB → market entry → SL at retest H/L (or recent H/L) → TP 1.5R or trail to day H/L or opposing AVWAP → no trade between close AVWAPs

---

### Bard FX Compensation Play (Nowick Strategy)

**Timeframe**: 15m. **Market**: AUDUSD, USDJPY, GBPUSD (primary); AUDJPY, USDCHF, AUDCHF (secondary). **Session**: 8am–2pm Sweden time = 2am–8am NY = 7am–1pm London. Can also test 2nd half of Asia and early NY.

**Core concept**: Nowick candle = a candle that opens and immediately moves in one direction with NO wick on one side (body only on that side). Acts as an imbalance similar to an FVG.

**Entry Steps**:
1. Identify trend direction on 15m
2. Look for a Nowick candle in the direction of the trend (bullish Nowick in uptrend, bearish Nowick in downtrend)
3. Wait for price to RETEST that Nowick candle within 9 candles
4. Enter on limit order at the retest of the Nowick candle's open/close

**SL**: Recent structural H/L with 3-pip buffer.
**TP**: 1:1 (fixed). No active trade management.

**Added confluences**: Support/resistance nearby in trade direction. Additional imbalances (FVGs, other Nowicks) between entry and TP add quality.

**Invalidations**:
- Nowick candle formed at a structural swing H/L (avoid)
- Price front-runs the entry and creates new H/L before retest
- Large FVG + Nowick imbalance sitting past your SL (reduces probability)
- US news within 1–2 hours of entry

**Rules**: If 2 Nowicks appear within 2–4 candles, can use a single entry between them or split risk. Nowick on 30m/1h → can switch to that TF for the 9-candle rule.

**Checklist**: Trend direction → Nowick candle in trend direction → no invalidations present → retest within 9 candles → limit entry at Nowick level → SL at structure H/L + 3pip buffer → TP 1:1 fixed

---

### 0xfibonacci Crypto Confluence (EMA + Volume Profile)

**Timeframe**: 1h. **Market**: BTC, ETH, SOL, LINK, BNB (crypto). **Session**: 8am–10pm NY (sometimes London session too).

**Indicators**: 200 EMA + Volume Profile (POC = Point of Control: peak volume level from swing high to swing low, row size ~2000).

**Core concept**: After a clear breakout, price will retest either the 200 EMA or a POC level. These are confluence points where institutional orders cluster.

**Entry Trigger 1 — Protected Retest** (two nearby levels = 200 EMA + POC both close):
- Limit entry at the retest zone (between the two levels)
- SL: beyond the 2nd key level (past both the EMA and POC)

**Entry Trigger 2 — Unprotected Retest** (only one level in play):
- Market entry after observing a reaction (price rejects the level with a reversal candle)
- SL: at the retest H/L (the wick/body low of the rejection candle)

**Entry Trigger 3 — Key Level Reclaim**: Price cuts through a key level and reclaims it shortly after.
- Market entry on the reclaim close
- SL: local H/L before the reclaim

**TP**: Range rebalancing move or continuation, minimum 2R. Move to b/e at halfway to TP. If 200 EMA taps before TP → consider closing early.

**Rules**:
- No trade if price is consolidating between reactive levels (POCs or 200 EMA)
- 200 EMA retests more reliable when EMA is sloped (not flat)
- Need a clean breakout before retest — no short-term chop
- High impact US news: avoid

**Checklist**: Mark recent POCs (HTF and local) → identify clear breakout → wait for retest of 200 EMA + POC (limit, Trigger 1) OR reaction to single level (market, Trigger 2) OR key level reclaim (Trigger 3) → TP 2R+ rebalance or continuation → b/e at halfway → no consolidation zones

---

### Trader Kane NQ Lab Model

**Timeframe**: 1m, 3m, or 5m execution; 4h + 1h context. **Market**: NQ (ES used for SMT). **Session**: 10am–1pm ET (best window).

**Core concepts**:
- **Premium/Discount**: Upper half of a price leg = premium; lower half = discount. Only long from discount, short from premium.
- **LLT (Logical Liquidity Target)**: First H or L that crosses the premium/discount midpoint — used as profit target for reversals.
- **Balanced vs Imbalanced**: If price has retraced to the midpoint of a prior move, it is "balanced." If not, it will likely balance in the future. Track this on 4h, 1h, and 5m.
- **SMT Divergence**: NQ vs ES correlation crack = manipulation signal.
- **iFVG (Inverse FVG)**: An FVG that price has closed through — now acts as S/R and entry trigger.

**Entry Trigger 1 — Reversal**: Wait for the 10am 4h candle to close. Then wait for ES and/or NQ to sweep the 10am 4h candle H/L AWAY from your trade direction. Then require BOTH: SMT Divergence (ES vs NQ) + iFVG on the 1m/3m/5m.
- Entry: on iFVG retest (limit) or buy/sell stop if strongly moving toward iFVG
- SL: recent H/L (or SMT invalidation level for a tighter stop)
- TP: LLT (first H/L through the premium/discount midline)
- B/e: once halfway to TP

**Entry Trigger 2 — Continuation**: LTF range rebalances (reaches midpoint) while HTF range is still unbalanced in same direction. Then require: SMT divergence + iFVG on 1m/3m/5m.
- Entry: same as Trigger 1
- SL: recent H/L
- TP: LLT or new H/L
- B/e: once halfway to TP

**Rules**:
- If SMT happens first, can use buy/sell stop if price is strongly approaching the iFVG
- If SMT happens second, can re-use earlier iFVGs as entry level
- Does not combine multiple consecutive FVGs — uses 3m or 5m instead of 1m in those cases

**Reversal Checklist**: 10am 4h candle closed → ES/NQ sweeps 4h candle H/L away from direction → SMT divergence confirmed → iFVG on 1/3/5m → entry → SL at H/L → TP at LLT → b/e halfway

**Continuation Checklist**: LTF balanced + HTF unbalanced (imbalance in direction) → SMT divergence → iFVG on 1/3/5m → entry → SL at H/L → TP at LLT or new H/L → b/e halfway

---

### Trader Mike Failed 2s Strategy

**Timeframe**: 1h (context/target), 15m (setup), 1m (execution). **Market**: ES, NQ (indices); could test 4h/1h/5m for forex. **Session**: NY 9:45am–4:00pm ET.

**Key definitions**:
- **#3 Candle (Engulfing)**: A candle that sweeps BOTH sides of the previous candle's H/L AND closes beyond the body of the previous candle. (Note: candles don't need to be different colors. Use Omar Agag's EBP definition: close past body, not just wick.)
- **Failed 2 Candle**: A candle that wicks past ONE side of the previous candle but FAILS to close (displace) past it. Failure to displace signals likely reversal.
- **LTF Shift**: MSB on 1m with a strong displacement close + FVG forming in the MSB move.

**Entry Steps**:
1. **Step 1 — HTF #3 Candle**: Wait for a 1h #3 (engulfing) candle to form. This candle's H/L becomes the target. If the target is hit before steps 2/3, NO TRADE.
2. **Step 2 — MTF Failed 2**: Wait for a 15m Failed 2 candle in line with the target direction (if target is higher: look for 15m Failed 2 that sweeps prior low but fails to close past it).
3. **Step 3 — LTF Shift**: After the Failed 2, check for a 1m MSB with strong close + FVG. If already formed, market enter. If not yet, wait for it. Best if entry is in premium/discount zone relative to the Failed 2.

**TP**: The H/L of the 1h #3 candle target (1:1 based on that distance). No active trade management.
**SL**: Set so TP = 1:1 risk/reward based on the target distance.

**Rules**:
- Stop trading after one loss
- No trade if strong opposing 15m candle (sweeps low AND closes past it) appears before LTF shift
- Avoid trading into an opposing 15m FVG before TP (unless FVG is the TP)
- Optional confluence: FVG "delivering" from a supporting FVG (the Failed 2 sits inside a prior FVG)

**Checklist**: 1h #3 candle forms (target = its H/L) → 15m Failed 2 in target direction (sweeps one side, fails to close past) → 1m MSB + FVG (LTF shift) → entry → SL/TP at 1:1 relative to 1h target → stop after 1 loss

---

### Waqar Asim Forex Scalping (Decisional S/D)

**Timeframe**: 1h (S/D zones), 15m (trend), 1m (execution). **Market**: EURUSD, GBPUSD. **Session**: 8–9am London = 3–4am NY (1h window); 2–3pm London = 9–10am NY (1h window). Low-spread broker required.

**Core concepts**:
- **Decisional Supply**: Last up-candle (OB) immediately before a large impulsive down move. Bonus if preceded by an inducement sweep.
- **Decisional Demand**: Last down-candle (OB) immediately before a large impulsive up move. Bonus if preceded by an inducement sweep.
- **Inducement**: LTF liquidity sweep (equal highs/lows wick through) followed by a BOS — signals who is in control.
- **Premium/Discount**: Only short in premium (above midpoint of recent range), only long in discount (below midpoint).

**Entry Steps**:
1. Identify trend via 1h + 15m (look for recent inducements showing buyer/seller control)
2. Determine if in premium (short bias) or discount (long bias)
3. Wait for MSB or BOS on 1m in trend direction
4. Wait for inducement into a LTF Decisional Supply/Demand zone (price sweeps a small equal-H/L then bounces)
5. Enter at the LTF S/D zone

**SL**: Fixed 5 pips (based on average London session move of 15–20 pips).
**TP**: 50% at 3R; 50% at 10R. If uncertain about 10R target: full TP at 3R.
**B/e**: After new internal H/L forms on 1m execution chart.

**Optional confluence**: SMT Divergence between EURUSD and GBPUSD.
**Invalidation**: Price moves beyond 50% of local range before entry (usually = 15–20 pip session move happened already).

**Rules**: Very patient model — most days no trade. Mark Asia session (midnight–6am UK = 19:00–1am NY) for additional context. Stop after one loss.

**Checklist**: Identify trend + premium/discount (1h/15m) → no invalidation (session move not yet used) → SMT Divergence optional → MSB/BOS on 1m → inducement into LTF Decisional S/D → entry → 5pip SL → b/e after new internal H/L → 50% at 3R, 50% at 10R (or full at 3R)

---

### JJ Simon Fair Value Theory NQ Strategy

**Timeframe**: 1m. **Market**: NQ. **Session**: 9:30–11:00am NY (primary); 2:00–3:00pm NY (secondary); could also test first 90 min after Asia/London opens.

**Fair Value Theory**: If there is no new information for the market to price in, price will likely revert to "fair value." JJ has identified two main fair value prices:
- 9:30am market open price = NY morning fair value
- 2:00pm price = NY afternoon fair value

**Timing logic**:
- First 10–15 min of each session window: look for **CONTINUATION** away from fair value (displacement in one direction)
- Rest of the trade window: look for **MEAN REVERSION** back to fair value

**Entry model**: Look for a Displacement Candle + BOS or MSB. Then market enter.
- **Displacement candle**: Strong close with counter-wick < 20% of the candle's distance from open to counter-wick extreme (mechanically: fib at 0/0.2/1 — wick must be within the 0.2 level). Larger candle size is optional but preferred.
- **BOS** = continuation (trend in same direction as displacement)
- **MSB** = mean reversion back to fair value

**SL distance (ATR-based)**:
- ATR > 20: 50-point SL, 75-point TP (1.5R)
- ATR 7–20: 25-point SL, 37.5-point TP (1.5R)
- ATR < 7: 16.5-point SL, 24.75-point TP (1.5R)

**TP**: Always 1.5R fixed. No active trade management.

**Rules**:
- Avoid first 3 minutes after 9:30 open
- 2nd attempt may be ok but collect data to confirm
- Session VWAP as optional confluence
- Can also trade 8:30am red folder news reversions (price reverting to pre-news fair value)
- Do not trade 2nd hour of each NY window (optimization: stick to first hour only)

**Checklist**: Mark 9:30am or 2pm fair value price → first 10–15min: displacement candle + BOS (continuation) → after 15min: displacement candle + MSB back toward fair value → ATR determines SL distance → TP 1.5R fixed → avoid first 3min, avoid 2nd hour of window

---

## Reasoning Quality Standards (Reminiscences + Market Wizards)

When writing the `reasoning` field in the signal JSON:
1. State which SPECIFIC level (exact price) is the structural support/entry zone.
2. State which candle pattern formed (e.g., "hammer with lower shadow 2.3× the body").
3. State the regime clearly (e.g., "4h uptrend, EMA50 rising, BTC neutral").
4. State the invalidation (exactly where the stop is and WHY that price is the invalidation).

Livermore: "I don't buy because a stock has gone up. I buy because the right thing has happened at the right time at the right place." — Your reasoning must reflect this specificity.

# ApexGrid (swarm v0) — Test Report
**Name: ApexGrid (confirmed). Paper / simulation
ONLY. `LIVE_MODE = False` everywhere. No API keys, no live trades.**

Data: real Binance.US klines, 2024-01-01 → 2026-11-09, no key.
1h: 25,050 bars/asset. 4h: 6,263 bars/asset. 15m: 100,200 bars/asset.
Fees 10 bps/side, slippage 5 bps, $1,000 notional/trade unless noted.
Kraken Funded (paper): make +12% ($1,200), never drop 3% ($300 max DD).

**Bottom line: the swarm does NOT hit the Kraken target. Nothing here is
proven comfortably profitable. The allocator funds exactly one strategy:
BREAKOUT, $10,000 of $10,000 (run 3, n=75, exp +$0.85 — real but
razor-thin). The other bright spot is Dump & Hedge on BTC 15m (positive
but unproven, n=18). Every invented strategy backtested negative and was
benched.**

## 1. Smoke tests — ALL PASS (24 checks, 0 failures)
`python3 smoke_test.py` — run 2026-11-10. All 6 agents instantiate and
tick; deliberate crash agent restarted 3x then benched while the other 5
kept ticking (fault isolation proven); Kelly old formula == $0 for all
inputs / fixed formula == 0.20 on a real edge; Bellman mints validate
clean (real USDT + JTO, placeholders gone); Bellman finds a planted 2%
cycle (net +$500.00 EXECUTE) and none on consistent rates; live guard
blocks `place_live_order()`; INTEL_BUS publish + sentiment; learning loop
verified — Q-table BUY 0.0 → 0.1 on a real win, TradeMemory reflects
every 10 trades, weights sum to 1. Ledger selftest: 6/6 checks pass.

## 2. Bellman paper-scan — 0 cycles on real data (expected, honest)
`python3 bellman_scan.py` — 1,044 real 1h snapshots, BTC/ETH/SOL cross
rates: **0 negative cycles found, 0 EXECUTE verdicts, survival rate 0%.**
Consistent CEX cross-rates have no free money in them; a scanner that
found profit there would be lying. Synthetic proof it works: planted 2%
mispricing → cycle USDC→BTC→SOL→USDC, gross +2.00%, net **+$500.00**,
verdict EXECUTE. No execution path earned until a live DEX quote feed
proves otherwise.

## 3. Backtest run 1 — 4h (before the RSI R:R fix)
6,263 bars/asset. FOMO_PANIC n=5, win 20%, exp **−$4.62**, net −$23.12.
Q_LEARNING n=29, win 21%, exp **−$8.20**, net −$237.91. BOLLINGER_FADE
n=6, exp **−$9.49**, net −$56.96. BREAKOUT n=11, exp **−$9.61**, net
−$105.72. RSI_MEAN_REVERSION: **0 trades** — the unsatisfiable R:R gate
(TP 2.0×ATR / SL 1.5×ATR = 1.33 < 1.5 gate). Allocation $0 everywhere.
Supervisor: 0 crashes. Full log: `backtest_run_4h.log`.

## 4. Backtest run 2 — 1h (RSI fix + regime gates + double-gate + Phoenix + Ghost + Echo)
25,050 bars/asset. Full log: `backtest_run_1h.log`. **WARNING: this run's
regime gate was broken (99.9% SIDEWAYS) — its RSI/Bollinger/BREAKOUT/ECHO
numbers are void. Run 3 supersedes them. Kept here as history.**

| Strategy | n | Win% | Avg win | Avg loss | Expectancy | PF | Net | Max DD | Proven? |
|---|---|---|---|---|---|---|---|---|---|
| RSI_MEAN_REVERSION | 12 | 50% | $28.11 | $21.04 | **+$3.54** | 1.34 | +$42.45 | $48.71 | No (n<30) |
| BOLLINGER_FADE | 27 | 30% | $32.68 | $18.43 | −$3.28 | 0.75 | −$88.62 | $121.23 | No |
| Q_LEARNING | 48 | 27% | $25.70 | $17.38 | −$5.71 | 0.55 | −$273.99 | $299.39 | **Yes — proven LOSER** |
| FOMO_PANIC | 3 | 0% | $0.00 | $12.09 | −$12.09 | 0.00 | −$36.26 | $36.26 | No |
| BREAKOUT | 0 | — | — | — | — | — | — | — | 0 trades (regime bug) |
| ECHO | 0 | — | — | — | — | — | — | — | 0 trades (regime bug) |

- **Q_LEARNING test split only (bars ≥ 17,535, frozen): n=0.** The frozen
  Q-agent made zero trades in the test period — it learned HOLD is
  safest, which is the correct lesson when every action loses money.
- **Allocation of $10,000 paper: $0.00 to every strategy** (no proven winners).
- **Supervisor:** all 6 agents live, 0 crashes, 0 restarts.
- **TradeMemory weights:** RSI 0.516, BOLLINGER 0.206, Q 0.1958, FOMO 0.0821.
  Reflections fired 10 times (every 10 trades) into `brain.json`.
- **INTEL_BUS:** 500 signals published; double-gate dropped 101.
- **Phoenix: 993 hibernations** — the freeze bug (see §7): bars ~16,590–
  25,040 had no trading after equity sat $356 below peak.
- **Kraken Funded (paper): total net −$356.42 (−3.56%), target $1,200 NOT
  HIT; swarm max drawdown $356.42 (3.56%), limit $300 BREACHED.**

## 5. Backtest run 3 — 1h v2 (regime fix + Phoenix fix)
25,050 bars/asset. Full log: `backtest_run_1h_v2.log`. This run supersedes
run 2 for BREAKOUT, ECHO, RSI and Bollinger — run 2's regime gate was
broken (99.9% SIDEWAYS), so its numbers for those four are void.

| Strategy | n | Win% | Avg win | Avg loss | Expectancy | PF | Net | Max DD | Proven? |
|---|---|---|---|---|---|---|---|---|---|
| BREAKOUT | 75 | 41% | $27.20 | $17.71 | **+$0.85** | 1.08 | +$63.87 | $226.43 | **Yes — first proven winner** |
| RSI_MEAN_REVERSION | 11 | 36% | $25.55 | $15.45 | −$0.54 | 0.95 | −$5.93 | $59.12 | No |
| Q_LEARNING | 67 | 36% | $26.96 | $17.47 | −$1.56 | 0.86 | −$104.31 | $182.08 | **Yes — proven loser** |
| BOLLINGER_FADE | 16 | 19% | $19.96 | $14.56 | −$8.08 | 0.32 | −$129.36 | $129.36 | No |
| FOMO_PANIC | 3 | 0% | $0.00 | $12.09 | −$12.09 | 0.00 | −$36.26 | $36.26 | No |
| ECHO | 0 | — | — | — | — | — | — | — | 0 trades (dormant producer) |

- **BREAKOUT is the first strategy to earn a PROVEN positive tag**
  (n=75, exp +$0.85) — thin edge (PF 1.08), but it meets the rule.
  **Allocation: BREAKOUT $10,000.00, everyone else $0.00.** The
  allocator works as designed.
- **RSI flipped negative** (exp −$0.54, n=11) vs run 2's +$3.54. Run 2's
  RSI positive was an artifact of the broken regime gate (it traded in
  all regimes mislabelled SIDEWAYS); with a real gate it only fires in
  true sideways bars and loses slightly. RSI is demoted from core.
- **Q_LEARNING improved** (−$1.56 vs −$5.71) but is still a proven loser.
  **Test split only (frozen): n=0 again** — the frozen Q-agent makes
  zero trades in the test period (it learned HOLD is safest).
- **ECHO: 0 trades in both main runs.** The ported EchoAgent is a
  dormant signal producer (strict FFT-slope + log-return shape gates);
  the looser NEW ECHO_TREND variant in the harness traded 404 times
  and benched at exp −$2.81.
- **Supervisor:** all 6 agents live, 0 crashes, 0 restarts.
- **TradeMemory weights:** BREAKOUT 0.4999 (top, correctly), Q 0.2151,
  RSI 0.2091, FOMO 0.0702, BOLLINGER 0.0057.
- **INTEL_BUS:** 500 signals published; double-gate dropped only 2.
- **Phoenix: 2 hibernations, 1 peak reset** — the fix worked (was 993
  hibernations in run 2). The swarm kept trading after the reset.
- **Kraken Funded (paper): total net −$211.98 (−2.12%), target $1,200 NOT
  HIT; swarm max drawdown $347.49 (3.47%), limit $300 BREACHED** — better
  than run 2 (−$356.42) but still breached. The swarm dipped $347 below
  peak, then recovered to −$212.

## 6. Experiments — 15m dump family (fast harness, `experiments.py`)
100,200 bars/asset, 30% size ($300), TP +5% / SL −10%, max hold 96 bars.

| Strategy | n | Win% | Avg win | Avg loss | Expectancy | PF | Net | Max DD | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| DUMP_HEDGE_15 (3 assets) | 164 | 59.1% | $9.65 | $13.57 | **+$0.16** | 1.03 | +$26.81 | $182.81 | Positive but ~breakeven |
| DUMP_HEDGE_15 (BTC only) | 18 | 72.2% | $7.03 | $2.82 | **+$4.29** | 6.47 | +$77.29 | $6.76 | Positive, unproven |
| DUMP_HEDGE_15 (ETH only) | 69 | 59.4% | — | — | −$0.14 | — | −$9.98 | $68.85 | Negative |
| DUMP_HEDGE_15 (SOL only) | 77 | 55.8% | — | — | −$0.53 | — | −$40.50 | $182.81 | Negative |
| DOUBLE_PANIC (3 assets, NEW) | 83 | 59.0% | $9.59 | $14.70 | −$0.36 | 0.94 | −$29.70 | $176.25 | **Benched** |
| DOUBLE_PANIC (BTC only) | 10 | 100% | $8.46 | $0.00 | +$8.46 | 999 | +$84.61 | $0.00 | Small-n luck |

The dump edge lives only on BTC. The RSI<25 confirmation filter made
DOUBLE_PANIC worse on ETH/SOL — benched, not improved.

## 7. Experiments — NEW 1h strategies (fast harness)
25,050 bars/asset, fees + slippage included.

| Strategy | n | Win% | Expectancy | Net | Max DD | Verdict |
|---|---|---|---|---|---|---|
| ECHO_TREND (NEW) | 404 | 43.3% | −$2.81 | −$1,133.97 | $1,192.04 | **Benched** |
| ASCETIX_SPOT (NEW) | 2,911 | 43.5% | −$0.68 | −$1,969.09 | $1,969.09 | **Benched** |
| META_LEARNER all (NEW) | 576 | 40.5% | −$3.79 | −$2,181.07 | $2,247.98 | **Benched as trader** |
| META_LEARNER test split (NEW) | 139 | 41.7% | −$3.45 | −$478.94 | $545.85 | **Benched as trader** |

META_LEARNER's Q-table did learn honestly: BREAKOUT Q −0.65 (TREND_UP),
ASCETIX_SPOT Q −0.69 (TREND_DOWN) — it learned the menu loses money.
By chosen strategy: ASCETIX n=377 net −$1,431.80; BREAKOUT n=127 net
−$438.91; BOLLINGER n=14; ECHO_TREND n=41; RSI n=17. Every menu item
loses. Full results: `experiments_results.json`.

## 8. Bugs found by the build (all fixed, all disclosed)
1. **Regime gate (indicators.py):** compared two 50-bar means ONE bar
   apart — the 0.5% threshold almost never fired, so 99.9% of 1h bars
   read SIDEWAYS and BREAKOUT/ECHO got 0 trades in run 2. Fixed: SMA
   now vs 50 bars ago. Distribution now ~40% up / ~40% down / ~15%
   sideways. Run-2 BREAKOUT/ECHO numbers are void; run 3 re-tests them.
2. **Phoenix freeze (backtest.py):** 993 hibernations froze ~35% of run 2
   — once equity sat >$300 below peak, the rule re-hibernated forever.
   Fixed: after 3 consecutive hibernations the peak resets to current
   equity and trading resumes.
3. **Ascetix cooldown not enforced:** first experiments run let it fire
   every bar (4,875 trades). Fixed: `simulate()` enforces `cooldown_bars`.
4. Earlier faults (from the original brief): lambda-`__init__` tuple bug,
   fake P&L engines, Kelly == $0, MEV/Jito, Bellman placeholder mints,
   UpsideOnly RSI R:R gate, Q-learning binary rewards — all fixed, see
   README "Faults fixed".

## 9. What still fails / what is unproven
- **No strategy has a comfortable edge.** The two proven-positive
  strategies are BREAKOUT (+$0.85/trade, n=75, PF 1.08) and Dump & Hedge
  3-asset (+$0.16/trade, n=164, PF 1.03) — both barely above breakeven.
  The best per-asset edges (Dump & Hedge on BTC, exp +$4.29) are still
  unproven by sample size (n=18).
- **Q-learning as a standalone trader is a proven loser** (−$1.56/trade,
  n=67 in run 3; −$5.71 in run 2). Kept only as the learning mechanism.
- **RSI's run-2 positive (+$3.54) was a regime-gate artifact** — with a
  real gate it is −$0.54 (n=11). Do not quote the run-2 RSI number.
- **Kraken target NOT hit in any run.** Best swarm result: −2.12%
  (run 3, DD breached at 3.47%).
- **Bellman: 0% cycle survival on real CEX rates.** No execution path.
- **The both-sides hedge leg of Dump & Hedge** (YES+NO ≤0.98) is
  prediction-market-only; not portable to spot. The spot "hedge" is
  30% sizing + SL −10%.
- **15m dump signals are rare:** 18 BTC dumps in ~2.9 years. This is a
  low-frequency edge by nature, not a daily income stream.
- **No live anything.** No keys, no orders. GitHub repo live and private: https://github.com/kevinleestites2-dev/ApexGrid (ApexGrid confirmed,
  Kevin confirming; he creates the empty repo at github.com/new).

---

# ApexGrid v1 — Test Report (2026-11-10)
**Paper / simulation ONLY. `LIVE_MODE = False` everywhere. No API keys, no live trades.**
Code: `experiments_v1.py` (fast harness, same fill/exit semantics as v0),
`smoke_v1.py` (28/28 checks pass). Full per-strategy numbers:
`experiments_v1_results.json` (81 entries incl. tuning variants).
Data: same real Binance.US klines as v0 (1h 25,050 bars/asset, 15m 100,200).
Fees 10 bps/side + 5 bps slippage. Kraken Funded (paper): +12% ($1,200),
never drop 3% ($300 max DD).

**Bottom line: v1 is BIGGER (23 agents) but still does NOT hit Kraken.**
The funded swarm is now Dump & Hedge only: **+$242.56 (+2.43%)** over
~2.9 years, maxDD $169.96 (within the $300 limit) — real, but a long way
from +$1,200. The grid family — the namesake — has only two positives,
both Echo-gated, both failing the Kraken drawdown limit, neither funded.
And v0's headline BREAKOUT number does not survive a clean re-test
(see §V1.1 — the most important finding in v1).

## V1.0 Smoke tests — 33/33 PASS
`python3 smoke_v1.py`. Every v1 signal fn returns valid (side, tp, sl)
or None on bars 200–2000; every grid variant runs without crashing;
breakout/dump factories, pairs stat arb, live guard all pass.
Two bugs were caught BY the smoke test and fixed before any backtest:
(a) LIQ_CASCADE first draft had TP below entry for a long (inverted
signal); (b) a second pass caught the short-side SL could sit below
entry when price had already broken the high. Both fixed in
`experiments_v1.py` (bounce-off-the-zone version).
A third bug — the Echo cache (see V1.7 #6) — was caught by a
reproducibility check DURING the write-up, not by the smoke test; a
regression check (`echo_agrees_order_independent`) was added to
`smoke_v1.py` afterwards and passes.

## V1.1 CORRECTION — v0's BREAKOUT "proven winner" does NOT reproduce
This is the biggest finding of v1, and it changes the v0 record.
- **Clean re-test of the faithful v0 BreakoutAgent signal** (0.5% buffer
  beyond the prior-20 CLOSE high/low, TP +3% / SL −1.5%, TREND/UNKNOWN
  regime): **n=2,869, win 34.0%, exp −$2.56/trade, PF 0.78, net −$7,341.94.**
  The signal itself LOSES money. It is **DEMOTED from "proven winner" to
  BENCHED as a signal.**
- Why did v0 say +$0.85 (n=75)? The v0 engine is not a clean per-strategy
  backtest: (1) TradeMemory **auto-suspends a whole symbol** when its
  cumulative PnL (across ALL strategies) drops below −$150, and
  `backtest.py` then skips every agent for that symbol for the rest of
  the run; (2) **brain.json persists across runs** — run 3 started with
  run 2's blacklist already loaded (BTC was already suspended; ETH was
  suspended during run 3; only SOL kept trading); (3) Phoenix hibernation
  halts entries at −$300 swarm DD; (4) the rotation cap blocks repeat
  entries on one asset. The raw BreakoutAgent tick fires **4,890 times**
  (BTC 1,118 / ETH 1,634 / SOL 2,138) — v0's 75 trades are what survived
  those gates, not what the strategy earned. The +$0.85 measures the
  engine's risk controls + luck, not a strategy edge. **Do not quote
  v0's BREAKOUT +$0.85 as a proven edge. The v0 README's "funded $10,000"
  allocation is withdrawn.**
- A partial check (truncate each asset's clean trade list at cumulative
  −$150) gives BTC 11 / ETH 50 / SOL 84 trades — it does NOT reproduce
  +$0.85 either, so the full v0 number is a compound of all four gates
  plus the carried-over brain. The honest conclusion stands regardless:
  **the breakout signal, tested clean, loses −$2.56/trade.**
- The suspension/Phoenix controls themselves are KEPT as risk controls
  (they demonstrably stop bleeding) — but they are not an edge, and no
  strategy is funded on an engine-gated number again. All v1 numbers
  below are clean-harness, per-strategy, no suspension, no Phoenix.

## V1.2 BREAKOUT tuning — faithful v0 base, 18 variants, ALL negative
Stage 1 (TP/SL/lookback, buffer 0.5%, no volume filter): best was
TP5/SL2/LB10, exp −$1.47. Stage 2 (buffer 0.3/0.5/1.0 × volume none/1.5x)
around it: **best overall TP5/SL2/LB10/BUF0.5/V1.5, n=1,788, exp −$0.63,
PF 0.96, net −$1,134.01** — still negative, but the volume filter and
wider TP are the two improvements that help most. The first v1 tuning
sweep (loose copy: no buffer, ATR exits, volume filter) gave n~2,800
and is **VOID** — it tested a different strategy; superseded by this one.
Full sweep in `experiments_v1_results.json` (BREAKOUTv0_*).
**Verdict: BREAKOUT is benched in every variant. Tuning cannot save it.**

## V1.3 GRID FAMILY — the namesake (1h, leg $200, re-anchor 168 bars)
Real multi-lot engine: buy a level on a dip, sell one level up, one lot
per level, fills at bar close + slippage, re-anchor every 168 bars or on
an 8% move (stop variants). Pooled across BTC/ETH/SOL; maxDD shown is
the pooled-trade-sequence figure, worst-asset DD is the per-asset
equity-curve figure.

| Strategy | n | Win% | Exp/trade | PF | Net | MaxDD | Verdict |
|---|---|---|---|---|---|---|---|
| GRID_SIDEWAYS_1PCT | 1,073 | 59.1% | −$0.85 | 0.74 | −$909.91 | $937.83 | **Benched** |
| GRID_ATR (true ATR spacing) | 3,750 | 67.0% | −$0.76 | 0.74 | −$2,836.25 | $3,048.48 | **Benched** |
| GRID_7LEVEL_1.5PCT | 2,477 | 58.0% | −$0.52 | 0.84 | −$1,288.32 | $1,462.48 | **Benched** |
| GRID_TREND_ARMED | 3,737 | 66.1% | −$0.55 | 0.82 | −$2,049.33 | $2,348.03 | **Benched** |
| GRID_FOMO_RSI40 | 3,246 | 62.1% | −$0.65 | 0.80 | −$2,110.36 | $2,326.28 | **Benched** |
| GRID_ECHO | 865 | 64.3% | **+$0.04** | 1.01 | **+$31.71** | $343.19 | **Positive but NOT funded** — see note |
| GRID_TIGHT_0.5PCT | 6,332 | 76.4% | −$0.51 | 0.79 | −$3,229.93 | $3,498.97 | **Benched** (fees eat the tight grid) |
| GRID_WIDE_2PCT | 1,531 | 54.0% | −$0.55 | 0.85 | −$847.48 | $995.58 | **Benched** |
| GRID_NOSTOP_1PCT | 2,614 | 74.9% | −$0.24 | 0.92 | −$620.39 | $981.59 | **Benched** |
| GRID_SIDEWAYS_NOSTOP | 1,027 | 67.7% | −$0.24 | 0.93 | −$247.31 | $666.09 | **Benched** |
| GRID_ECHO_NOSTOP | 784 | 67.1% | **+$0.17** | 1.05 | **+$133.10** | $541.63 | **Positive but NOT funded** — see note |
| GRID_WIDE2_NOSTOP | 1,295 | 66.7% | −$0.06 | 0.99 | −$72.50 | $549.81 | **Benched** |

**Why grids lose:** the win rate looks good (54–76%) because most lots
sell one level up for a small win — but the losses are the lots bought
5–8% down that get closed at the re-anchor/stop for −$8 to −$10 each,
against +$3 to +$5 wins. The 8% stop is the main loss source (no-stop
variants improve every grid by ~$0.30–$0.60/trade), but removing it
leaves huge unrealised drawdowns instead. **GRID_ECHO** is the only
stop-grid that is positive after the Echo-cache fix (exp +$0.04,
PF 1.01, net +$31.71, n=865) — but +$0.04/trade is noise-thin (the fix
itself flipped it from −$0.04) and its maxDD is $343.19, which breaches
the Kraken $300 limit, so it is **NOT funded**. **GRID_ECHO_NOSTOP**
is the other positive grid (exp +$0.17, PF 1.05, net +$133.10, n=784)
— it passes the exp>0/n≥30 rule on paper, but its maxDD is $541.63
(worst asset $540.84), which **breaches the Kraken $300 limit**, and it
was found by a post-hoc variant search after GRID_ECHO looked closest
— so it is **NOT funded** and is treated as unproven until it survives
a fresh out-of-sample test. The grid family earns its place in the name
as a real, tested family — not as a funded strategy yet.

## V1.4 MYTHOS 10 + MetaTrader + VWAP + NEW combos (1h, $1,000 notional)
All negative. The honest baseline: a no-edge strategy loses ~$3/trade
here (fees 10bps/side + 5bps slippage ≈ $3 per $1,000 round trip), so
anything near −$3 is random, anything better than −$3 has a little edge,
anything worse is actively bad.

| Strategy | n | Win% | Exp/trade | Net | Verdict |
|---|---|---|---|---|---|
| SUPERTREND (corrected) | 1,940 | 38.2% | −$3.95 | −$7,666.30 | **Benched** |
| MACD_CROSS | 3,581 | 42.6% | −$2.92 | −$10,473.30 | **Benched** (random) |
| GOLDEN_CROSS | 241 | 33.6% | −$1.24 | −$298.99 | **Benched** (best of the MYTHOS set, still negative) |
| STOCHASTIC | 582 | 40.2% | −$3.42 | −$1,987.91 | **Benched** |
| FIB_PULLBACK | 1,558 | 32.9% | −$3.66 | −$5,706.08 | **Benched** |
| ICHIMOKU | 993 | 42.5% | −$2.57 | −$2,555.28 | **Benched** |
| VOL_PRICE_DELTA | 3,118 | 46.2% | −$1.81 | −$5,644.16 | **Benched** |
| VOL_EXPANSION | 1,525 | 40.2% | −$3.41 | −$5,201.09 | **Benched** |
| VWAP_REVERSION | 5,412 | 26.9% | −$2.94 | −$15,907.93 | **Benched** (churn: 5,412 trades) |
| MOMENTUM_BREAKOUT | 78 | 42.3% | −$0.52 | −$40.79 | **Benched** (closest single-position, still negative) |
| LIQ_SWEEP | 2,812 | 46.4% | −$3.14 | −$8,829.82 | **Benched** |
| CVD_DIVERGENCE_PROXY | 6 | 16.7% | −$25.37 | −$152.22 | **Benched** (proxy almost never fires) |
| OI_SPIKE_PROXY | 5,627 | 44.6% | −$2.49 | −$14,036.96 | **Benched** (churn) |
| LIQ_CASCADE_PROXY | 6,876 | 34.8% | −$3.17 | −$21,788.74 | **Benched** (churn; bounce version) |
| FUNDING_PROXY | 6,833 | 49.3% | −$3.33 | −$22,727.27 | **Benched** (proxy carries no edge) |
| BREAKOUT_ECHO_NEW | 307 | 41.0% | −$2.10 | −$644.60 | **Benched** (Echo filter makes Breakout worse, not better) |
| TREND_ASSASSIN_NEW | 2,090 | 27.3% | −$2.60 | −$5,437.86 | **Benched** |
| STAT_ARB_BTCETH (synthetic pair) | 1,473 | 36.3% | −$0.49 | −$725.35 | **Benched** (best "almost" — ratio reversion has a hint of edge, fees eat it) |

**Supertrend bug (found and fixed in v1):** the first v1 Supertrend
implementation had the final-band trailing conditions inverted, so the
trend almost never flipped (BTC/ETH: 1 flip in 25,050 bars, n=1 trade).
Fixed to the standard bands (upper only moves down while price is below
it; lower only moves up while price is above it): 695–840 flips/asset,
n=1,940, exp −$3.95. The buggy n=1 number is void.

## V1.5 DUMP & HEDGE tuning — the one family that works (15m, $300 size)
32 variants on BTC, then the best validated on all assets. Robust set
(2% threshold, n≈60–69 on BTC, all PROVEN on BTC alone):
T2/TP3/SL5/H96 exp +$0.68, net +$45.24, maxDD $83.16;
T2/TP8/SL10/H96 exp +$0.57; T2/TP5/SL10/H96 exp +$0.48.
Best-by-exp across the 32 (selection-bias caveat — it was picked because
it was best): **T3/TP8/SL10/H96 — BTC n=18, exp +$6.03, net +$108.46,
maxDD $6.76; validated on all assets n=161, win 58.4%, exp +$1.51,
PF 1.26, net +$242.56, maxDD $169.96 — PROVEN.** The 4%/5% thresholds
look spectacular per trade (exp +$8 to +$13) but on n=3–6 — small-n luck,
not an edge. Full sweep: `experiments_v1_results.json` (DUMP_BTC_*).

## V1.6 Funded swarm (v1) vs Kraken target
Funded: **DUMP_BEST_ALL_ASSETS only — net +$242.56 (+2.43% on $10,000),
maxDD $169.96 (WITHIN the $300 limit).** GRID_ECHO_NOSTOP is positive
but excluded (DD $541.63 breaches). Everything else is benched.
**Kraken target +$1,200: NOT HIT. Kraken DD limit: not breached by the
funded swarm.** The funded swarm makes money, slowly (~55 trades/year
across 3 assets) — it is a real edge, not a Kraken pass. Do NOT take the
Kraken challenge on this yet.

## V1.7 Bugs found in v1 (all fixed, all disclosed)
1. **Supertrend band inversion** (see V1.4): trend almost never flipped.
   Fixed to standard final bands; flips 695–840/asset.
2. **LIQ_CASCADE inverted TP/SL** (caught by smoke_v1, twice): first
   draft had TP below entry for a long; second pass caught the short-side
   SL could sit below entry. Rewritten as a bounce off the zone.
3. **v0 BREAKOUT number is an engine artifact** (see V1.1): not a code
   bug, a measurement bug — persistent brain.json + pair suspension +
   Phoenix + rotation. Withdrawn, not patched over.
4. **First v1 BREAKOUT tuning sweep tested the wrong strategy** (loose
   experiments.py copy, no buffer, ATR exits): n~2,800, all negative.
   Void; superseded by the faithful-v0-base sweep in V1.2.
5. **Grid pooled PF was a placeholder** in the first draft of the grid
   aggregation (summed stats, not pooled trades). Fixed: pool the trade
   lists and compute PF/exp from pooled trades; worst-asset DD reported
   alongside the pooled DD.
6. **Echo cache order-dependence** (`experiments.py` `echo_agrees`,
   found during the v1 write-up, 2026-11-10): the cache was keyed by
   `i//16` but the value was computed at the CURRENT bar `i`, so the
   cached value depended on which bar of a 16-bar block first called it.
   Two runs sharing a Ctx gave different answers (GRID_ECHO_NOSTOP:
   n=784 fresh vs n=776 after other variants ran on the same ctx;
   GRID_ECHO flipped sign, −$0.04 → +$0.04, after the fix). Fixed:
   compute at the block's first bar `i0 = (i//16)*16` and cache under
   `i0`. Regression check `echo_agrees_order_independent` added to
   `smoke_v1.py` (33/33 pass). All Echo-gated numbers in this report
   (GRID_ECHO, GRID_ECHO_NOSTOP, BREAKOUT_ECHO_NEW) are the post-fix
   values; pre-fix Echo numbers are void. (Note: v0's ECHO-family
   numbers in the v0 section above were computed with the same buggy
   cache — they were already benched and negative, so no v0 verdict
   changes, but their exact figures are not reproducible post-fix.)

## V1.8 What still fails / what is unproven
- **No strategy has a comfortable edge.** The only funded edge (Dump &
  Hedge, exp +$1.51) makes +2.43% in ~2.9 years — Kraken needs +12%.
- **Grid is the namesake and it loses.** 10 of 12 grid variants negative;
  the 2 positive ones (GRID_ECHO exp +$0.04, GRID_ECHO_NOSTOP exp +$0.17)
  both fail the Kraken DD test ($343.19 and $541.63 vs $300) and are not
  funded. Grid needs a genuinely different idea (e.g. grid only in proven
  sideways regimes with a volatility filter, or grid as an execution layer
  for a proven signal) — not more spacing variants.
- **BREAKOUT is dead as a signal** (18 faithful variants, all negative).
- **Proxies carry no edge:** funding, CVD, OI, liquidation proxies all
  test at or below the −$3 random baseline. Real feeds would be needed
  to test the real versions.
- **Selection bias warning:** DUMP_BEST and GRID_ECHO_NOSTOP were both
  picked as "best of many variants" — their numbers are optimistic until
  they survive an out-of-sample / forward paper test.
- **No live anything.** No keys, no orders. Repo is private; code is
  NOT pushed yet (parent pushes after Kevin approves).

---

# ApexGrid v2 — Test Report (2026-11-10)
**Paper / simulation ONLY. `LIVE_MODE = False` everywhere. No API keys, no live trades, no Kraken challenge entered, no GitHub push.**
Code: `experiments_v2.py`, `smoke_v2.py` (**30/30 checks pass**). Full numbers: `experiments_v2_results.json`.
Data: real Binance.US klines 2024-01-01 → 2026-11-10 (1h 25,050 bars/asset, 4h 6,263, 15m 100,200).
Split: **train 2024–2025, test 2026-01-01 → 2026-11-10 (out-of-sample)**. Two cost modes per strategy: **HARD** (10 bps/side + 5 bps slip = 0.30% RT, as v0/v1) and **KRAKEN** (spread-only ~0.05% RT: 2 bps/side + 1 bp slip).
Gates: expectancy > 0, PF > 1.2, n ≥ 100 (all-data), maxDD ≤ $300 on $10k. A strategy joins the stack only if it also passes on TEST (exp > 0, PF > 1.2, n_test ≥ 30, test DD ≤ $300).

**Bottom line: v2 tests 14 strategies and NONE passes the gates. The stacked swarm is EMPTY in both cost modes — there is nothing to fund, and the Kraken target (+$1,200) is not hit by any combination. The only strategy with a positive expectancy in the out-of-sample test is Dynamic Grid — and it fails the drawdown gate by 3.4x. The next-closest, Pullback in Kraken mode, is positive in test (+$1.51/trade) but fails PF (1.06) and DD ($779.73).**

**Context that matters:** 2026, the out-of-sample year, is a bear market on the test data — buy-and-hold 2026: BTC −14.8%, ETH −28.9%, SOL −31.5% (vs 2024–25: BTC +87.5%, ETH +13.0%, SOL +21.2%). Trend strategies that made money in the 2024–25 bull mostly gave it back in 2026. That does not excuse them — the Kraken challenge is regime-blind — but it explains the train/test flip, and it means a strategy that only works in a bull market is not a Kraken strategy.

## V2.0 Smoke tests — 30/30 PASS
`python3 smoke_v2.py`. All 13 signal fns return valid long-only (side, tp, sl) or None on bars 300–3000; Trend Assassin fires 97 times on BTC 1h and its CROWD exit is reached in simulation; TrendRider simulates (n=449); Dynamic Grid, Kalman pairs and Momentum rotation all run. One bug caught BY the smoke test and fixed before any backtest: **Range trading could fire below the 20-bar low, putting the stop ABOVE the entry** (tp=52,184 / c=51,176 / sl=51,294 on BTC 1h). Fixed: skip when close is already below the range low — that is a range break, not a buy.

## V2.1 Results — HARD mode (0.30% round trip)

| Strategy | Train n / exp / PF / net / DD | Test n / exp / PF / net / DD | Verdict |
|---|---|---|---|
| TREND_FOLLOW_4H | 238 / −$10.10 / 0.55 / −$2,403 / $2,420 | 101 / −$12.58 / 0.50 / −$1,271 / $1,714 | **Benched** |
| PULLBACK_4H | 224 / +$4.94 / 1.18 / +$1,107 / $683 | 127 / −$2.57 / 0.90 / −$326 / $1,053 | **Benched** (train-positive, test-negative) |
| RSI2_RANGE_1H | 433 / −$6.57 / 0.19 / −$2,844 / $2,846 | 115 / −$6.44 / 0.16 / −$741 / $741 | **Benched** |
| VWAP_BOUNCE_15M | 320 / −$8.73 / 0.51 / −$2,795 / $2,937 | 177 / −$7.20 / 0.52 / −$1,274 / $1,297 | **Benched** |
| VWAP_RETEST_15M | 574 / −$5.07 / 0.44 / −$2,912 / $2,912 | 206 / −$6.76 / 0.30 / −$1,393 / $1,402 | **Benched** |
| TRENDRIDER_1H | 935 / −$8.37 / 0.46 / −$7,824 / $7,882 | 407 / −$8.13 / 0.38 / −$3,307 / $3,346 | **Benched** (worst net in v2) |
| TURTLE_4H | 236 / +$1.04 / 1.08 / +$244 / $460 | 103 / −$1.42 / 0.90 / −$146 / $811 | **Benched** |
| TURTLE_TP1_4H | 429 / −$1.98 / 0.81 / −$848 / $979 | 164 / −$4.77 / 0.60 / −$782 / $935 | **Benched** (tight TP is worse) |
| EMA_RIBBON_15M | 4,756 / −$5.94 / 0.17 / −$28,263 / $28,267 | 1,848 / −$6.02 / 0.16 / −$11,130 / $11,130 | **Benched** (fee-eaten scalp; 6,604 trades) |
| RANGE_1H | 791 / −$5.46 / 0.63 / −$4,316 / $4,433 | 392 / −$6.02 / 0.59 / −$2,362 / $2,411 | **Benched** |
| VOL_BREAKOUT_1H | 603 / −$4.63 / 0.65 / −$2,793 / $2,827 | 347 / −$5.25 / 0.58 / −$1,823 / $1,874 | **Benched** |
| TREND_ASSASSIN_1H | 377 / −$8.22 / 0.58 / −$3,101 / $3,101 | 117 / −$8.53 / 0.54 / −$998 / $998 | **Benched** (Gravia's coolest idea does not survive contact) |
| MEAN_REV_ZSCORE_1H | 157 / −$8.26 / 0.33 / −$1,298 / $1,298 | 77 / −$6.27 / 0.49 / −$483 / $483 | **Benched** (like the Bollinger family in v1) |
| DYN_GRID_1H | 1,666 / +$2.25 / 2.51 / +$3,751 / $2,491 | 546 / +$1.64 / 1.88 / +$897 / $1,019 | **Positive but NOT funded** — DD breaches $300 by 3.4x |
| KALMAN_PAIRS_1H | 568 / −$3.90 / 0.59 / −$2,213 / $2,257 | 256 / −$2.44 / 0.68 / −$626 / $716 | **Benched** |
| MOMENTUM_ROT_1H | 66 / +$5.59 / 1.17 / +$369 / $403 | 23 / −$7.85 / 0.76 / −$180 / $372 | **Benched** (train-positive, test-negative; n=89 total < 100) |

## V2.2 Results — KRAKEN mode (spread-only ~0.05% RT)

| Strategy | Train n / exp / PF / net / DD | Test n / exp / PF / net / DD | Verdict |
|---|---|---|---|
| TREND_FOLLOW_4H | 238 / −$6.62 / 0.68 / −$1,575 / $1,749 | 100 / −$7.84 / 0.64 / −$784 / $1,359 | **Benched** |
| PULLBACK_4H | 224 / +$8.53 / 1.33 / +$1,912 / $616 | 127 / +$1.51 / 1.06 / +$192 / $780 | **Closest to passing** — positive in test, fails PF (1.06 < 1.2) and DD ($780 > $300) |
| RSI2_RANGE_1H | 433 / −$1.78 / 0.62 / −$772 / $830 | 115 / −$1.64 / 0.62 / −$189 / $217 | **Benched** |
| VWAP_BOUNCE_15M | 320 / −$3.95 / 0.72 / −$1,263 / $1,516 | 177 / −$2.40 / 0.80 / −$425 / $463 | **Benched** |
| VWAP_RETEST_15M | 574 / −$0.27 / 0.96 / −$157 / $510 | 206 / −$1.97 / 0.70 / −$405 / $419 | **Benched** (train ≈ breakeven, test negative) |
| TRENDRIDER_1H | 933 / −$4.55 / 0.65 / −$4,250 / $4,320 | 404 / −$4.12 / 0.61 / −$1,665 / $1,712 | **Benched** — the claimed 67.9% win / 1.42% DD does NOT reproduce |
| TURTLE_4H | 236 / +$2.70 / 1.24 / +$638 / $393 | 103 / +$0.69 / 1.05 / +$71 / $682 | **Benched** — positive in test, fails PF and DD |
| TURTLE_TP1_4H | 429 / −$0.38 / 0.96 / −$161 / $467 | 164 / −$2.89 / 0.74 / −$473 / $651 | **Benched** |
| EMA_RIBBON_15M | 4,756 / −$1.36 / 0.73 / −$6,470 / $6,499 | 1,848 / −$1.34 / 0.72 / −$2,471 / $2,594 | **Benched** (even at Kraken costs the 0.4% TP is too small) |
| RANGE_1H | 791 / −$0.66 / 0.94 / −$521 / $1,558 | 392 / −$1.23 / 0.89 / −$481 / $990 | **Benched** |
| VOL_BREAKOUT_1H | 603 / +$0.17 / 1.02 / +$101 / $463 | 347 / −$0.45 / 0.95 / −$158 / $353 | **Benched** (train ≈ breakeven, test negative) |
| TREND_ASSASSIN_1H | 377 / −$3.25 / 0.80 / −$1,225 / $1,374 | 117 / −$3.88 / 0.75 / −$454 / $633 | **Benched** |
| MEAN_REV_ZSCORE_1H | 157 / −$3.47 / 0.57 / −$545 / $594 | 77 / −$1.56 / 0.81 / −$120 / $291 | **Benched** — win rate only 14.3% in test (avg win $46.46, avg loss $9.56: the mean rarely comes back before the −1.5% stop or the time stop) |
| DYN_GRID_1H | 1,666 / +$2.74 / 2.85 / +$4,558 / $2,470 | 546 / +$2.13 / 2.15 / +$1,161 / $1,007 | **Positive but NOT funded** — exp and PF pass, DD $1,007 breaches $300 by 3.4x |
| KALMAN_PAIRS_1H | 568 / −$1.50 / 0.82 / −$852 / $981 | 256 / −$0.04 / 0.99 / −$11 / $277 | **Benched** — effectively breakeven in test at Kraken costs (DD within limit, PF 0.99) |
| MOMENTUM_ROT_1H | 66 / +$6.28 / 1.20 / +$415 / $388 | 23 / −$7.22 / 0.78 / −$166 / $365 | **Benched** (train-positive, test-negative; n=89 total < 100) |

## V2.3 Stacked swarm — EMPTY in both modes
No strategy passes the test gate in either cost mode, so the stack has no members: **hard n=0, net $0.00; Kraken n=0, net $0.00. Kraken target +$1,200: NOT HIT.** For reference, the funded v1 swarm (Dump & Hedge only, +$242.56) is NOT included in v2's stack — v2 tests new strategies only; Dump & Hedge still stands as the sole funded edge from v1, and it was not re-tested here.

## V2.4 The three nearest misses — and why they still fail
1. **Dynamic Grid (re-centring, ADX<25).** The only strategy positive in test in BOTH modes (hard test +$1.64/trade, PF 1.88; Kraken test +$2.13, PF 2.15, net +$1,161 in test alone — tantalisingly close to the $1,200 target on test net alone). Profile in Kraken test: 95.2% win, avg win $4.17, avg loss $38.83 — the classic grid shape: hundreds of tiny wins, a few big closing losses when held lots are finally realised. DD is the killer: $1,007 test / $2,470 train. Scaling the grid down 10x (leg $20) would put DD ~$100 but net ~$116 — the net/DD ratio (~1.15 in test) cannot reach $1,200 inside $300. It needs a genuinely smaller drawdown, not smaller size: e.g. a hard stop on unrealised drawdown, or grid only in proven sideways regimes with a volatility filter. **Not funded.**
2. **Pullback in Uptrend (Kraken mode).** Train is the best single-position result in v2 (exp +$8.53, PF 1.33, net +$1,912) and test stays positive (+$1.51, net +$192) — the ONLY single-position strategy positive in test in Kraken mode besides Turtle. But PF 1.06 and DD $779.73 in test fail the gates, and in hard mode it flips negative in test (−$2.57). It is the most promising single-position arm for a v3 tweak (tighter stop? trend filter?), not a fund.
3. **Kalman Pairs (Kraken mode).** Test exp −$0.04, PF 0.99, net −$11.38, DD $277.05 — breakeven, and the ONLY strategy whose test DD is inside the $300 limit besides Mean Reversion ($291.14, but exp −$1.56). The long-only rotation adaptation keeps ~none of the published pairs edge (the short leg was half of it, as predicted in the Plan B hunt). **Not funded.**

## V2.5 Bugs / corrections found in v2 (all fixed, all disclosed)
1. **Range signal stop-above-entry** (smoke test, see V2.0): fired below the 20-bar low. Fixed by skipping when close < range low.
2. **Dynamic Grid PF=999 / $0 DD (first v2 run, VOID).** Pooling realised grid trades across the train/test split gives a fake PF of 999 and $0 drawdown, because losing lots are held unrealised and only winning lots ever close. The first run's grid numbers (train net +$6,242, PF 999, DD $0) are **void and are not quoted anywhere else in this report**. Fixed: the grid is now run separately on train and on test, closing all lots at the split boundary, and the reported DD is the equity-curve DD (realised + unrealised), worst single asset. Corrected numbers are in V2.1/V2.2 (train net +$3,751 hard / +$4,558 Kraken; test net +$897 hard / +$1,161 Kraken; DD $2,491/$1,019 hard, $2,470/$1,007 Kraken).
3. **EMA Ribbon is a 15m proxy, not 5m.** No 5m Binance.US klines exist in the data (only 15m/1h/4h). The spec's 5m timeframe and 1m confirmation candle are approximated on 15m bars. Its failure is therefore a failure of the 15m version; the true 5m version is untested, not proven false.
4. **Kalman pairs uses fixed $1,000 notional, not risk sizing.** A spread-implied stop does not map cleanly to a single-asset stop distance, so risk-% sizing was not applied to this arm (disclosed in code). Its PnL is comparable to the other arms' $1,000-notional scale.
5. **Momentum rotation n=89 total (66 train / 23 test).** Weekly rebalancing over ~2.9 years gives too few samples to pass the n≥100 gate even if it were positive — it is not (test −$7.22/trade).

## V2.6 What still fails / what is unproven
- **14 strategies tested, 0 funded.** The pattern across v0/v1/v2 is now consistent: on real Binance.US data with fees, almost every named strategy loses or breaks even, and the ones that win in-sample (Pullback, Turtle, Momentum rotation, Trend Following in train) flip or fade out-of-sample in the 2026 bear year.
- **Dump & Hedge (v1, +$242.56, +2.43%) remains the ONLY funded edge in ApexGrid.** It was not re-tested in v2. Nothing in v2 adds to it.
- **The Kraken challenge is not enterable on this evidence.** No stack passes the gates; no single strategy passes test exp>0 + PF>1.2 + DD≤$300.
- **No live anything.** No keys, no orders, no challenge entry, no entry fee. Code is NOT pushed to GitHub (report first, Kevin decides).

## V2.7 Mean reversion as the backbone — 24 variants, ALL FAIL
Kevin's call (2026-11-10): mean reversion (#14) is the backbone of v2 — test it first / hardest. Done: 24 pre-specified variants (z −1.5 / −2 / −2.5 × exit at mean / 5-period MA × ADX<25 gate on / off × 1h / 15m), BTC/ETH only, long-only, RSI(14)<30, SL below recent low capped at −1.5%, risk 0.25%/trade. Code: `experiments_v2_mr.py`. Full numbers: `experiments_v2_mr_results.json` (48 entries: 24 variants × 2 cost modes).

**Verdict, stated plainly as ordered: the backbone idea did NOT hold. Not one of the 24 variants passes the test gate in either cost mode. There is no core arm to stack around, so no backbone swarm was built.**

Every variant is negative on expectancy in BOTH splits and BOTH modes — this is not a borderline result and not a cost-mode artifact. Best test expectancy in hard mode is −$5.59/trade (z−2.0, exit mean, no ADX gate, 15m, PF 0.41); best in Kraken mode is −$0.81/trade (same variant, PF 0.86). Best test PF anywhere is 0.91 (z−2.5, exit mean, ADX<25, 15m, Kraken). The gates need exp > 0 and PF > 1.2; nothing comes close.

| Variant (Kraken mode, test split) | n | Win% | Avg win | Avg loss | Exp | PF | Net | DD |
|---|---|---|---|---|---|---|---|---|
| z−2.0, mean, no ADX, 15m (best exp) | 947 | 20.7% | $23.94 | $7.26 | −$0.81 | 0.86 | −$762 | $1,039 |
| z−1.5, mean, no ADX, 15m | 1,129 | 20.8% | $23.45 | $7.49 | −$1.05 | 0.82 | −$1,184 | $1,432 |
| z−1.5, sma5, ADX<25, 1h (best PF-ish) | 84 | 25.0% | $22.70 | $9.04 | −$1.11 | 0.84 | −$93 | $237 |
| z−2.0, mean, ADX<25, 1h (original #14) | 77 | 14.3% | $46.46 | $9.56 | −$1.56 | 0.81 | −$120 | $291 |
| z−2.5, mean, ADX<25, 15m (best PF) | 220 | — | — | — | −$1.70 | 0.91 | −$374 | $412 |

Why it fails — the pattern is the same in all 24 variants: **the win rate is ~15–25%, and the mean almost never comes back before the stop or the time stop.** The TP (the 20-period mean, or the 5-period MA) is far away — price is 2+ SD below the mean, so the round trip to the mean is a big move — while the SL is capped at −1.5%. Wins are big when they land (avg win $20–$47) but rare; losses are small and constant (avg loss $7–$14). At a 20% win rate you need avg win ≈ 4× avg loss just to break even, and the data gives ~2–3×. Loosening the threshold to z−1.5 (more trades, n=1,129 in test on 15m) does not help — win rate stays ~21%. Tightening to z−2.5 (rarer, deeper dips) does not help either — win rate stays ~15–25% and n falls. Removing the ADX gate (trading in trends too) makes it worse, not better: the no-ADX variants have the worst drawdowns (up to $6,650 hard mode). The ADX<25 gate helps the drawdown but not the expectancy. The 15m versions trade far more often (n up to 1,129 in test) and lose more in total; the 1h versions trade less and lose less per trade in Kraken mode, but still lose.

**Selection-bias note:** the best of 24 variants was picked on the test split and it STILL loses (−$0.81/trade). There is no cherry-picked version of this idea that passes. A forward-paper retest would not rescue it — the failure is in-sample and out-of-sample, in both cost modes, across every knob. **Mean reversion is benched as the backbone, and as a strategy. It joins RSI(2) and Bollinger in the benched mean-reversion family (v0/v1/v2).**


---

# ApexGrid v3 — Test Report (2026-11-10)
**Paper / simulation ONLY. `LIVE_MODE = False` everywhere. No API keys, no live trades, no Kraken challenge entered, no GitHub push.**
Code: `experiments_v3.py`, `smoke_v3.py` (**18/18 checks pass**), `fetch_1h_4h.py`. Full numbers: `experiments_v3_results.json` (146 entries). Full log: `v3_run.log`.
Data: same real Binance.US klines as v2 (1h 25,050 bars/asset, 4h 6,263, 15m 100,200), through 2026-11-10. Split: **train 2024–2025, test 2026-01-01 → 2026-11-10 (out-of-sample)**. Two cost modes: **HARD** (0.30% RT) and **KRAKEN** (spread-only ~0.05% RT).
Gates (v3): expectancy > 0, PF > 1.2, n ≥ 100 (all-data), **STATIC DD ≤ $300** (min equity ≥ $9,700). Peak DD reported alongside, not gated.

**Bottom line: v3 still does NOT hit the Kraken target. The stacked swarm of NEW v3 passers is EMPTY in both modes (n=0, net $0) — same as v2. The static-drawdown correction changes the numbers but not the verdicts: no benched strategy is re-funded, because every strategy that now passes the DD gate still fails expectancy/PF. The one thing that survives is the old edge: Dump & Hedge holds up on the 2026 hold-out in Kraken mode (n=33, exp +$1.36, PF 1.30, net +$44.78, static DD $43.43) — the ONLY gate-passer in the entire 146-entry v3 file. It remains the sole funded edge, and it is nowhere near $1,200. The grid fixes prove a hard trade-off: every fix that contains the drawdown kills the expectancy, and every fix that keeps the expectancy keeps the drawdown above $950. Mean reversion is dead twice over. And the random-entry baseline beats most real signals on 1h at Kraken costs — the signals are worse than random entries with the same exits.**

## V3.0 Smoke tests — 18/18 PASS
`python3 smoke_v3.py`. Live guard; static-DD maths on synthetic trades ([+100, −250] → static $150, peak $250, minEq $9,850; win-then-dip → static stays $0 while peak DD is $50 — the static floor does not trail); fetcher probe (3 fresh live 1h bars from Binance.US into a temp dir, never touching `data/`); splits sane on all timeframes; daily resample (1,045 bars, test 314); random baseline deterministic per seed; Dump simulator runs; MR v2 signals valid; short-diagnostic engine runs short-only; 4h/daily signals valid. **Grid base reproduces v2 exactly on trades** (Kraken train net +$4,558.15, n=1,666; test net +$1,161.33, n=546) — so every fix comparison built on it is valid. The DD numbers do NOT reproduce v2's, on purpose: see §V3.1.

## V3.1 CORRECTION — drawdown is STATIC, and v2 understated the grid's DD
**Kraken Funded uses a STATIC 3% drawdown, fixed from starting balance** — verified from Kraken's own pages, 2026-11-10 (kraken.com/learn/how-do-prop-trading-firms-work, kraken.com/gb/learn/best-crypto-prop-firms): "Kraken Funded uses a single static limit", "a fixed 3% drawdown floor with no separate daily limit", "the floor is $9,700" on a $10,000 account. Traders do not get leverage and all trades are limited to 1x exposure, and Kraken Funded has zero trading commissions — which also supports the Kraken cost mode (spread-only ~0.05%) as the challenge-relevant one, with hard mode (0.30%) as the pessimistic bound. Caveat: one third-party roundup (daytrading.com) lists a 5% max DD for Kraken Funded; Kraken's own pages say 3%, so v3 gates on 3%. **v0/v1/v2 measured drawdown from PEAK equity, which is stricter than Kraken.** v3 measures both and gates on static — but nothing is silently re-funded on static DD alone; peak DD is reported alongside every number.
How much does static help? A lot on paper, not enough in practice. Kraken mode, test split, static vs peak DD: Pullback $405 vs $780; Turtle $590 vs $682; Kalman $160 vs $277; Mean Reversion $291 vs $291; RSI2 $217 vs $217. In train the gap is bigger (Pullback $22 vs $616; Turtle $20 vs $393 — train equity almost never fell below its starting balance). **Four §7 strategies pass the static DD gate in the Kraken test (RSI2, Volume Breakout, Mean Reversion, Kalman) — and ALL FOUR still fail on expectancy/PF.** The binding constraint is now the edge, not the drawdown. In hard mode, zero §7 strategies pass static DD in test.
**Second correction, found while building the grid fixes: v2 UNDERSTATED the Dynamic Grid's drawdown by ~2.2x.** v2 reported max(worst-single-asset equity DD, pooled realised-trade DD) = $1,007 in the Kraken test. But the grid runs on all three assets at once on one $10k account, and in the 2026 bear year all three hold underwater lots at the same time — their unrealised losses ADD. The true combined account curve (all three assets' realised + unrealised equity summed bar by bar) gives **test static DD $1,441, peak DD $2,187** (train: static $318, peak $3,334). The base grid breaches the $300 static limit **even in train** ($318 Kraken, $372 hard). v3 reports the combined curve as primary, worst-asset DD alongside. (Same lesson, smaller: v1's Dump maxDD $169.96 was computed on trades pooled in asset order; the chronological pooled peak DD is $198.68 hard / $180.95 Kraken. Net/exp/PF reproduce v1 exactly.)

## V3.2 Random-entry baseline — the signals are worse than random (1h, Kraken costs)
Random entries (Bernoulli per bar when flat: p=0.01 on 1h, 0.04 on 4h), same exits as a typical strategy (TP +2% / SL −1.5%, 100-bar hold, risk 0.5%/trade), 3 seeds each, same two cost modes. Win rate ~47–49% on 1h Kraken (avg win ~$38–39 vs avg loss ~$31 — the +2/−1.5 asymmetry).

| Baseline | Test exp (mean of 3 seeds) | Test PF | Test net | Test static DD | All-data exp / PF |
|---|---|---|---|---|---|
| RANDOM 1h, hard | −$2.67 | 0.86 | −$531 | $660 | −$4.39 / 0.78 |
| RANDOM 1h, kraken | **+$2.14** | 1.13 | **+$428** | $158 | +$0.41 / 1.03 |
| RANDOM 4h, hard | −$8.29 | 0.62 | −$1,605 | $1,616 | −$6.69 / 0.68 |
| RANDOM 4h, kraken | −$3.49 | 0.82 | −$683 | $830 | −$1.90 / 0.90 |

Read it carefully. **At hard costs even random entries lose** (−$2.67 on 1h, −$8.29 on 4h) — fees and the exit structure are a real part of the problem. **At Kraken costs on 1h, random entries are roughly breakeven to slightly positive in test** (exp +$2.14, PF 1.13; all-data exp +$0.41, PF 1.03 — within noise of zero: per-trade σ ≈ $35, n ≈ 200/seed, so SE ≈ $2.50/trade). Most real v2 signals LOSE money in that same Kraken test (−$1.50 to −$8.13/trade) — **they are worse than random entries with the same exits.** So it is both: exits/fees eat the edge at hard costs, AND the signals add negative value on 1h. On 4h random loses clearly in both modes, so 4h signal losses are exits/fees plus signals together. **Random is NOT a strategy and is never funded** (PF 1.13 < 1.2, all-data exp ≈ $0, and it is random) — it is a yardstick, and most of the menu measures short against it.

## V3.3 Dump & Hedge 2026 hold-out — HOLDS UP (Kraken mode), weakens (hard mode)
v1 tuned T3/TP8/SL10/H96, $300 size, re-tested on 2026 out-of-sample only. It was picked from 32 tuned variants, so this is the honest check.

| Dump & Hedge | Full n / exp / PF / net | 2026-only n / exp / PF / net / sDD / pDD |
|---|---|---|
| Hard (0.30%) | 161 / +$1.51 / 1.26 / +$242.56 | 33 / +$0.63 / 1.13 / +$20.95 / $48.73 / $61.49 **[fail: PF]** |
| Kraken (~0.05%) | 161 / +$2.23 / 1.41 / +$359.03 | 33 / +$1.36 / 1.30 / +$44.78 / $43.43 / $59.09 **[PASS-2026]** |

The full-sample hard numbers reproduce v1 exactly (n=161, exp +$1.51, PF 1.26, net +$242.56) — the simulator is faithful. **Verdict: it holds up, it does not collapse.** In Kraken mode the 2026 hold-out passes the test gate (exp>0, PF 1.30, n=33, static DD $43) — the only gate-passer in v3. But it is weaker out-of-sample (2026 exp is ~60% of full-sample in Kraken mode, ~40% in hard mode), and in hard mode it fails the PF gate (1.13). Per-asset 2026 (Kraken): BTC n=4, 4 wins, exp +$10.42, PF 999 — **small-n luck, not proof** (4 trades); ETH n=14, exp −$1.03, net −$14.47 — still negative in 2026; SOL n=15, exp +$1.17, net +$17.57. **Dump & Hedge remains the sole funded edge (unchanged from v1).** n=33 in 2026 is thin; it earns a continued funded slot, not a bigger one. Full-data static DD is $0.48 (Kraken) — the equity curve almost never went below its starting balance.

## V3.4 Dynamic Grid drawdown fixes — every fix that contains DD kills the edge
Base: the only v2 strategy positive in test (Kraken test exp +$2.13, PF 2.15, net +$1,161) — but under the honest combined curve its test static DD is $1,441 (4.8x the limit) and peak DD $2,187. Goal: static DD ≤ $300 AND PF > 1.5. Each fix tested separately and combined, both cost modes (Kraken test shown; hard is worse in the same direction).

| Fix (Kraken test) | n | Exp | PF | Net | Static DD | Peak DD | Verdict |
|---|---|---|---|---|---|---|---|
| BASE (v2) | 546 | +$2.13 | 2.15 | +$1,161 | $1,441 | $2,187 | FAIL (DD 4.8x) |
| ADX cutoff 15 | 150 | −$0.10 | 0.98 | −$16 | $715 | $771 | FAIL — kills the edge |
| ADX cutoff 20 | 354 | +$1.55 | 1.64 | +$550 | $957 | $1,336 | FAIL — PF up, DD still 3.2x |
| Cap open inventory 3 lots | 88 | −$1.73 | 0.67 | −$152 | $550 | $615 | FAIL — kills the edge |
| Cap open inventory 5 lots | 151 | −$0.94 | 0.79 | −$141 | $873 | $940 | FAIL — kills the edge |
| Hard exit on grid break | 546 | −$0.44 | 0.82 | −$242 | $446 | $466 | FAIL — flips negative; the DGT hold IS the edge |
| Spacing scaled to volatility (ATR) | 672 | +$1.86 | 2.16 | +$1,247 | $2,231 | $2,826 | FAIL — DD worse, not better |
| Hard stop on unrealised DD $100 | 55 | −$4.21 | 0.36 | −$231 | $104 | $171 | FAIL — DD passes, expectancy destroyed (halted) |
| Hard stop on unrealised DD $150 | 87 | −$2.58 | 0.54 | −$224 | $181 | $247 | FAIL — same pattern (halted) |
| COMBINED (ADX20 + maxlot5 + break + ATR + DDstop150) | 437 | +$0.34 | 1.18 | +$148 | **$28.50** | **$151.99** | FAIL — DD passes both, PF 1.18 < 1.2, train NEGATIVE (exp −$0.16, net −$119), all-data PF 1.01 |
| COMBINED, no break-exit | 114 | −$0.52 | 0.87 | −$59 | $78 | $416 | FAIL — negative in test |

**Goal met by NONE.** The pattern is the whole story: capping inventory (3/5 lots) starves the grid of its small wins while the remaining lots still carry big losses; the break-exit realises the losses the DGT hold was deferring (train flips negative too, Kraken exp −$0.09); the unrealised-DD stop fires exactly when lots are deepest underwater and converts unrealised DD into realised losses, then halts the grid (n collapses to 55–87 in test); ATR spacing makes the DD worse. The combined fix is the closest thing to a pass on drawdown (static $28.50, peak $151.99 — both inside the limits) and it still fails, because its PF is 1.18 and it loses money in train. **The grid's edge IS its willingness to hold underwater lots. You cannot have both the edge and the drawdown limit.** Scaling the grid down does not help either (v2's note stands): leg $20 would put DD ~$100 but net ~$116 — the net/DD ratio cannot reach $1,200 inside $300. Dynamic Grid stays benched.

## V3.5 Mean reversion v2 — dead twice over (27 variants × 2 modes, ALL FAIL)
Wide stops / time exits instead of the −1.5% stop that killed v2: SL −1.5%/−3%/−5%, time exit 24h/48h (1h) / 96 bars (15m), exit at the mean, z −1.5/−2/−2.5, 1h and 15m, ADX<25, BTC/ETH only. **Not one of the 54 runs passes the test gate in either mode.** Best test expectancy anywhere is −$0.34/trade (z−2.5, SL−3%/−5%, 48h, 1h, Kraken, PF 0.96, n=74, win 16.2%); best PF anywhere is 0.96. Every variant is negative on expectancy in both splits and both modes.
The diagnostic that matters: **SL −3% and SL −5% give IDENTICAL results in nearly every row.** The stop is `max(5-bar low, entry × (1 − sl%))`, and the 5-bar low is almost always inside 3% of entry, so the wider cap never binds — the "wide stop" barely changes anything. 24h vs 48h barely matters either. The failure is not the stop: price 2 SD below the 20-period mean simply does not come back to the mean within 24–48 hours, and the win rate stays ~16–17% on 1h (~20% on 15m). Mean reversion is benched as the backbone and as a strategy — confirmed by v2 (24 variants) and v3 (27 variants). It joins RSI(2) and Bollinger in the benched mean-reversion family.

## V3.6 4h / daily versions — TrendRider daily looks great on n=15 (do NOT fund it)
Best v2 strategies (Trend Following, Pullback, TrendRider, Turtle) on 4h and daily bars, long-only. Daily bars are resampled from the 1h klines (1,045 bars/asset, test 314); no daily file exists yet (`fetch_1h_4h.py` can fetch 1d to rebuild them). Trend Following / Pullback / Turtle on 4h are the v2 runs themselves, re-reported under static DD in §V3.7.

| Strategy (Kraken test) | n | Exp | PF | Net | Static DD | Peak DD | Verdict |
|---|---|---|---|---|---|---|---|
| TREND_FOLLOW daily | 11 | −$10.57 | 0.57 | −$116 | $116 | $254 | Benched (n=11) |
| PULLBACK daily | 7 | +$13.60 | 1.47 | +$95 | $0 | $203 | Benched — n=7, noise |
| TURTLE daily | 21 | −$3.62 | 0.70 | −$76 | $160 | $160 | Benched — train was +$3.14/PF 1.29, flips in test |
| TRENDRIDER 4h | 114 | −$14.48 | 0.41 | −$1,651 | $1,651 | $1,671 | Benched — catastrophic |
| TRENDRIDER daily | 15 | **+$40.02** | **3.36** | **+$600** | **$0** | $152 | **Benched — n=15.** Train is also positive (+$12.53, PF 1.46, n=22), all-data n=37, exp +$23.68, PF 2.03, net +$876. It looks like the best thing in v3 and it is 15 test trades over a 314-bar test window, each trade lasting up to 100 days (ladder 30/60 bars = 30/60 days on daily). **Do not fund, do not chase — it needs a forward-paper test, not capital.** Flagged here so nobody quotes the PF 3.36 without the n=15. |

DIAG-SHORT (shorts are NOT Kraken-eligible — 1x spot, no leverage; diagnostic only, never gated, never stacked): Turtle short on 4h, Kraken test n=155, exp −$1.41, PF 0.87, net −$219, static DD $239, peak DD $631. Shorts do not save Turtle either.

## V3.7 Full v2 14-strategy set under STATIC drawdown — verdicts unchanged, reasons changed
Exp/PF/net reproduce v2 exactly (verified on every strategy). Under the static gate, 0 of 14 pass in either mode. Kraken-mode test split (static DD / peak DD alongside):

| Strategy | Test n / exp / PF / net | Static DD | Peak DD | Verdict |
|---|---|---|---|---|
| TREND_FOLLOW_4H | 100 / −$7.84 / 0.64 / −$784 | $1,191 | $1,359 | Benched |
| PULLBACK_4H | 127 / +$1.51 / 1.06 / +$192 | $405 | $780 | Benched — positive, fails PF and static DD |
| RSI2_RANGE_1H | 115 / −$1.64 / 0.62 / −$189 | $217 ✓ | $217 | Benched — passes static DD, fails exp/PF |
| VWAP_BOUNCE_15M | 177 / −$2.40 / 0.80 / −$425 | $432 | $463 | Benched |
| VWAP_RETEST_15M | 206 / −$1.97 / 0.70 / −$405 | $405 | $419 | Benched |
| TRENDRIDER_1H | 404 / −$4.12 / 0.61 / −$1,665 | $1,665 | $1,712 | Benched |
| TURTLE_4H | 103 / +$0.69 / 1.05 / +$71 | $590 | $682 | Benched — positive, fails PF and static DD |
| TURTLE_TP1_4H | 164 / −$2.89 / 0.74 / −$473 | $473 | $651 | Benched |
| EMA_RIBBON_15M | 1,848 / −$1.34 / 0.72 / −$2,471 | $2,471 | $2,594 | Benched |
| RANGE_1H | 392 / −$1.23 / 0.89 / −$481 | $481 | $990 | Benched |
| VOL_BREAKOUT_1H | 347 / −$0.45 / 0.95 / −$158 | $273 ✓ | $353 | Benched — passes static DD, fails exp/PF |
| TREND_ASSASSIN_1H | 117 / −$3.88 / 0.75 / −$454 | $633 | $633 | Benched |
| MEAN_REV_ZSCORE_1H | 77 / −$1.56 / 0.81 / −$120 | $291 ✓ | $291 | Benched — passes static DD, fails exp/PF |
| DYN_GRID_1H | 546 / +$2.13 / 2.15 / +$1,161 | $1,441 | $2,187 | Benched — positive, DD 4.8x static limit (combined curve, §V3.1) |
| KALMAN_PAIRS_1H | 256 / −$0.04 / 0.99 / −$11 | $160 ✓ | $277 | Benched — breakeven, passes static DD, fails exp/PF |
| MOMENTUM_ROT_1H | 23 / −$7.22 / 0.78 / −$166 | $365 | $365 | Benched (n=89 total < 100) |

Hard mode is worse in the same direction (test static DD: best is Kalman $628; nothing ≤ $300). **Stacked swarm: EMPTY in both modes (n=0, net $0). Kraken target +$1,200: NOT HIT.** Including the pre-existing Dump & Hedge edge, the Kraken-mode stack is Dump only: full net +$359.03, 2026 net +$44.78 — 3.7% of the target in the hold-out year.

## V3.8 What still fails / what is unproven
- **No NEW strategy passes the v3 gates.** The only gate-passer in the whole v3 file is Dump & Hedge in Kraken mode on its 2026 hold-out (§V3.3). Everything else — 14 re-run strategies, 11 grid fixes, 27 mean-reversion variants, 4h/daily versions — fails.
- **The Kraken challenge is not enterable on this evidence.** No stack passes the gates; the funded edge (Dump & Hedge) makes +$44.78 in the 2026 hold-out year at Kraken costs. Do NOT take the challenge on this.
- **Small-n traps flagged, not funded:** TrendRider daily (test PF 3.36, n=15), Pullback daily (PF 1.47, n=7), Dump BTC 2026 (PF 999, n=4). A PF of 999 on 4 trades is not an edge.
- **Bugs / corrections found in v3 (all disclosed):**
  1. **v2 understated the Dynamic Grid's drawdown ~2.2x** (§V3.1): the combined account curve replaces the max(worst-asset, pooled-realised) hybrid. Base grid test static DD $1,441 / peak $2,187, not $1,007.
  2. **v1's Dump maxDD was asset-ordered** ($169.96); chronological pooled peak DD is $198.68 hard / $180.95 Kraken. Net/exp/PF reproduce exactly.
  3. **Mean-reversion SL −3% ≡ SL −5%** (§V3.5): the 5-bar-low stop binds first, so the wider cap never engages. The stop was never the binding constraint.
  4. **No new fake runs.** The v2 grid PF=999 run stays void; PF=999 appears in v3 only in labelled small-n per-asset slices, never as a strategy result.
- **No live anything.** No keys, no orders, no challenge entry, no entry fee. Code is NOT pushed to GitHub (report first, Kevin decides).

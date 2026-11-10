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

# Swarm Trading Bot v0 — "Something Magical, Something Legendary"

Built from inspiration across **all** of Kevin's trading bots — not a copy
of any one of them. The magic is the assembly: the swarm-training embryo
from OpenAgora, the emotion brain from Gravia-Prime, the regime gates from
MYTHOS, the double-gate discipline from UpsideOnly, the memory from
MetaTrader, the router from OpenTrade, the cycle hunter from
BELLMAN-SCANNER, and the recovery spine from Phoenix. Forged into one
fault-isolated, honest, paper-only swarm.

**Paper / simulation ONLY. `LIVE_MODE = False` everywhere. No API keys,
no exchange credentials, no live trades. If any code tries to place a
live order, `place_live_order()` in `backtest.py` raises and logs it.**

## The target (Kraken Funded rules, paper)
- Make **+12%** on $10,000 paper capital ($1,200).
- Never drop **3%** from peak equity ($300 max drawdown).
- v0 does **not** hit the target (see `test_report.md` for the honest
  numbers). Nothing here is claimed profitable, "best in the world", or
  100% — the numbers are what they are, and the allocator funds only
  proven winners: in run 3 that is BREAKOUT alone, $10,000 of $10,000
  (n=75, exp +$0.85 — a real but razor-thin edge).

## Name & GitHub home — ApexGrid (confirmed)
**Name: ApexGrid.** Kevin offered it twice and confirmed it — this is the bot's name.
- **GitHub home is live: https://github.com/kevinleestites2-dev/ApexGrid — private, created 2026-11-10 by Zapia, first code push 2026-11-10 (commit 60774389827db8954f1d8b679126449275135691, branch main).**
- It stays **private** until the bot proves itself on paper (Kraken target: +12%, never drop 3%). Public only if/when it earns it.
- Local build lives in `~/workspace/goals/swarm-training-trading-bot/files/swarm-v0/`; the `data/` folder (47 MB of Binance klines) is NOT pushed — re-fetch it with `fetch_15m.py` / the Binance.US public API, no key needed.

## The learning loop (paper trading + learning is the core)
1. **Paper trade** — every signal fills at the next bar's open on real
   Binance.US history; every fill is recorded in the honest ledger with
   real entry/exit prices, fees and slippage.
2. **Q-learning learns from expectancy, not win/loss** — reward is
   `clip(pnl / risk, -1, 1)`; the Q-table updates by the Bellman equation
   with the REAL next state at exit. It trains on the first 70% of bars
   and is frozen on the last 30% so the reported numbers are a real test.
3. **TradeMemory scores everything** — recency-decayed weighted score
   (0.92/trade, 20-trade window), 0.05 allocation floor, auto-blacklist
   at -$150 per pair, per-regime memory, confidence calibration, and a
   **reflection every 10 recorded trades** (best/worst strategy, suspended
   pairs, calibration errors) written into `brain.json`.
4. **Meta Selector moves capital to winners** — Bayesian score
   `(2+wins)/(4+trades)` + TradeMemory weights + asset rotation cap;
   capital only flows to strategies with expectancy > 0 AND n >= 30.
   In run 3 that earned exactly one strategy money: **BREAKOUT,
   $10,000 of $10,000** (n=75, exp +$0.85). Everyone else gets $0 —
   the allocator is doing its job by refusing to fund unproven or
   losing strategies.

## Strategy selection — my picks (evidence, not hype)
Kevin delegated strategy selection: pick by backtest expectancy, risk
(max drawdown vs the Kraken 3% / $300 floor), and code quality. **Included
does not mean funded.** Every agent runs, publishes to the INTEL_BUS and
learns — but the Meta Selector only funds strategies with expectancy > 0
AND n >= 30. Right now that is $0 to everyone.

| Strategy | Role | Evidence | Verdict |
|---|---|---|---|
| **DUMP_HEDGE_15** (port, Kevin's favourite) | Core — 15m panic-dump fade | 3 assets, 15m: n=164, win 59.1%, exp **+$0.16**/trade, PF 1.03, net +$26.81, maxDD $182.81 — technically positive, but the edge lives **only on BTC** (n=18, exp +$4.29, net +$77.29, maxDD $6.76); ETH exp −$0.14, SOL exp −$0.53 | **CORE ON BTC ONLY.** ETH/SOL benched. Per-asset n is still <30, so even the BTC edge is unproven — but it is the best risk-adjusted signal in v0. |
| **DOUBLE_PANIC** (NEW) | — | 3 assets, 15m: n=83, win 59.0%, exp **−$0.36**/trade, net −$29.70. BTC-only looked perfect (n=10, win 100%, exp +$8.46) but ETH/SOL killed it (SOL exp −$2.90) | **BENCHED.** The RSI<25 confirmation filter made it worse, not better. The BTC-only 100% was small-n luck. |
| **BREAKOUT** (port) | **CORE — first proven winner, funded $10,000** | Run 3 (fixed regime): n=75, win 41%, exp **+$0.85**/trade, PF 1.08, net +$63.87, maxDD $226.43. Run 2's 0 trades were the regime bug. | **CORE. Thin edge (PF 1.08) — real, but barely above breakeven. The allocator funds it 100% because it is the only proven winner.** |
| **RSI_MEAN_REVERSION** (port) | — | Run 3: n=11, exp −$0.54, net −$5.93. Run 2's +$3.54 was an artifact of the broken regime gate (it traded in all regimes mislabelled SIDEWAYS). | **DEMOTED from core.** Negative with a real gate. |
| **Q_LEARNING** (port) | Learning core — the learner itself | Run 3: n=67, exp −$1.56, net −$104.31 **[PROVEN loser]** (improved from −$5.71 in run 2); frozen test split: **0 trades** (it learned HOLD is safest — the correct lesson when every action loses) | **BENCHED as a trader, KEPT as the learning mechanism.** Powers META_LEARNER. |
| **BOLLINGER_FADE** (port) | — | Run 3: n=16, exp −$8.08, net −$129.36 | **BENCHED.** Negative expectancy. |
| **ECHO** (port) / **ECHO_TREND** (NEW) | — | Standalone: 0 trades in both main runs (dormant producer). ECHO_TREND: n=404, exp −$2.81, net −$1,134, maxDD $1,192 | **BENCHED.** Real signal, negative expectancy. |
| **ASCETIX_SPOT** (NEW) | — | n=2,911, exp −$0.68, net −$1,969, maxDD $1,969 | **BENCHED.** No edge; fees eat it. |
| **META_LEARNER** (NEW) | — | n=576, exp −$3.79; test split exp −$3.45 | **BENCHED as a trader, KEPT as proof the learner works** — its Q-table correctly learned BREAKOUT/ASCETIX lose (Q −0.65/−0.69). |

## Dump & Hedge — which version was ported (Kevin's favourite)
Kevin: "dump in 15 minute dumping and hedge." The source is
`OpenTrade/zeus_prime_v2.py` L603 (`DumpAndHedgeStrategy`), with an older
copy in `trade.py` / `trade_meta.py`.
- **The "15 minute" is the market window, not the dump window.** It
  watches BTC/ETH/SOL/XRP **15-min Polymarket markets** and detects a dump
  in the **first 2 minutes** of the market. There is no separate "15-min
  dump window" variant in any repo — the 15 refers to the market length.
- **Ported version = the zeus copy:** YES/NO side drops **≥3%** (trade.py's
  older copy uses 15%) → buy the dumped side at **30% of normal size**,
  TP **+5%**, SL **−10%**.
- **The hedge leg (YES+NO ≤ 0.98 → buy BOTH sides) is prediction-market
  only** and is NOT portable to spot crypto — there is no YES/NO pair on
  a spot exchange. In the spot port the "hedge" is the risk control
  itself: 30% sizing + SL −10%. The both-sides leg stays as a
  prediction-market paper-scan idea, not a spot trade.
- **Spot translation (what was actually tested):** on 15m Binance.US bars,
  a bar whose low is ≥3% below its open = the dump; buy at the next
  bar's open (no lookahead), 30% size ($300), TP +5% / SL −10% from the
  signal close, max hold 96 bars.
- **Result (3 assets, 15m, 100,200 bars each): n=164, win 59.1%, exp
  +$0.16/trade, PF 1.03, net +$26.81, maxDD $182.81 — technically
  positive (n>=30, exp>0) but essentially breakeven. The edge lives
  only on BTC (n=18, exp +$4.29, net +$77.29, maxDD $6.76); ETH
  (exp −$0.14) and SOL (exp −$0.53) are slightly negative. Verdict:
  core slot on BTC only; ETH/SOL benched.**

## NEW strategies invented in v0 (not Kevin's old code)
Rule: a new strategy only counts as "proven" if it backtests POSITIVE on
expectancy on real history, with fees + slippage, and survives the Kraken
3% drawdown test. **None of the three below earned a funded spot.**
- **DOUBLE_PANIC** (NEW, 15m) — Dump & Hedge panic-fade + FOMO/PANIC
  confirmation: the ≥3% dump AND RSI(14) < 25 must agree. BTC-only
  looked perfect (n=10, win 100%, exp +$8.46, maxDD $0.00) — but across
  3 assets it is n=83, exp −$0.36, net −$29.70. The confirmation filter
  made it worse, not better. **Benched.**
- **ECHO_TREND** (NEW, 1h) — Echo FFT cycle + shape match, gated to TREND
  regime, with a Trend-Assassin-style crowd exit (volume climax). n=404,
  win 43.3%, exp −$2.81, net −$1,134, maxDD $1,192 — **benched**.
- **ASCETIX_SPOT** (NEW, 1h) — Ascetix 4-signal confluence adapted to
  spot 1x, no leverage: momentum + RSI zone + volume spike + bar
  pressure, 3/4 must agree, 25% size, 15-bar cooldown. n=2,911, exp
  −$0.68, net −$1,969 — **benched**. (The original Ascetix targets
  Polymarket BTC 15-min Up/Down with funding-rate + liquidation-flow
  signals; those need live feeds, so the spot version uses price/volume
  proxies. The proxies carry no edge.)
- **META_LEARNER** (NEW, 1h) — Q-learning that learns WHICH strategy to
  trust in WHICH regime (state = regime, action = strategy, reward =
  expectancy-normalised pnl/risk; trains first 70%, frozen last 30%).
  n=576, exp −$3.79; test split n=139, exp −$3.45 — **benched as a
  trader**. The mechanism itself works: its Q-table learned BREAKOUT
  (Q −0.65) and ASCETIX_SPOT (Q −0.69) lose money in trend regimes.
- **Bellman → Ghost stealth execution** (proposed, NOT built): Bellman
  finds the cycle, Ghost-style execution splits it. Not built because
  Bellman's survival rate on real data is 0% — there is no cycle to
  execute yet.

## How to run
```bash
cd ~/workspace/goals/swarm-training-trading-bot/files/swarm-v0
python3 smoke_test.py     # MUST pass before any sim (24 checks, all passing)
python3 backtest.py       # 1h backtest, BTC/ETH/SOL, 2024-01-01 -> now
python3 experiments.py        # fast harness: 15m dump family + new 1h ideas
python3 experiments.py dump   # 15m track only (needs data/*_15m.json)
python3 experiments.py new1h  # new 1h strategies + meta-learner only
python3 bellman_scan.py  # Bellman paper-scan over real 1h closes
```

## Files
| File | What it is |
|---|---|
| `config.py` | Paper rules: capital, fees, slippage, Kraken targets, Phoenix + Ghost + double-gate constants. `LIVE_MODE=False`. |
| `ledger.py` | Honest ledger (reused from `hidden_files/honest_ledger.py`, selftest passes). Every fill needs a real entry + exit price; fees + slippage always subtracted; expectancy scoring; sample_ok at n>=30. |
| `data/` | Real Binance.US klines, no key. `*_1h.json` (25,050 bars/asset, main run), `*_4h.json` (6,263 bars/asset), `*_15m.json` (100,200 bars/asset, Dump & Hedge track). Binance.com was geo-blocked (451) from this VM, so Binance.US is the source. No random walk, no invented prices. |
| `indicators.py` | RSI (Wilder), ATR, Bollinger, SMA, volume avg, MYTHOS-style regime (50-bar SMA slope — fixed, see "Faults fixed" #8). |
| `experiments.py` | Fast harness for new/ported ideas: precomputes indicators once, O(n) loop, same fill/exit semantics as backtest.py. Tests DUMP_HEDGE_15, DOUBLE_PANIC (15m), ECHO_TREND, ASCETIX_SPOT, META_LEARNER (1h). Results in `experiments_results.json`. |
| `fetch_15m.py` | Fetches 15m klines from Binance.US (public, no key). |
| `strategies.py` | 6 agents, each with a plain `__init__` (the lambda-tuple bug that killed Gravia-Prime cannot recur). |
| `intel_bus.py` | INTEL_BUS — shared signal bus. |
| `memory.py` | TradeMemory port (MetaTrader). |
| `selector.py` | Meta Strategy Selector / Router (OpenAgora + OpenTrade). |
| `runner.py` | Supervisor: fault isolation, restart up to 3x, then bench. |
| `kelly.py` | Fixed binary Kelly (see "Faults fixed"). |
| `bellman.py` / `bellman_scan.py` / `bellman_mints.py` | Bellman-Ford negative-cycle scanner, paper-scan only, corrected mints. |
| `backtest.py` | Engine: fills at next bar open (no lookahead), TP/SL/time-stop/max-hold, Phoenix hibernate, double-gate, Ghost slippage model, Kraken Funded metrics, Q-learning train/test split. |
| `smoke_test.py` | 24 checks incl. crash-isolation, Kelly, mints, Bellman, live guard, learning loop. All passing. |
| `brain.json` | TradeMemory persistence (written by backtest runs). |
| `test_report.md` | Actual test output + backtest numbers. |

## Where every idea came from (provenance)

### Gravia-Prime — the 26 (design doc, `swarm-bot-design-doc.md`)
| Idea | Status in v0 |
|---|---|
| ★ **FOMO/PANIC EmotionDetector** — 4-signal composite (RSI 78/22, 3x volume, 1.5% velocity, swarm sentiment), 3-of-4 confirms, contrarian, TP 2.5% / SL 1%, 10-bar time stop, 3-loss breaker, $300 loss limit | **Ported** as `FomoPanicAgent`. Sentiment is a price-breadth proxy (labelled as such) — the recovered file had no live INTEL_BUS feed. |
| ★ **Ghost Strike** — stealth execution, splits positions across wallets with randomised sizes/delays + decoy orders | **Modelled, not literally ported.** High-confidence fills (>= 0.80) are modelled at 2 bps slippage instead of 5 bps. The literal 5-wallet splitting is not simulated; the approximation is disclosed in `config.py`. |
| ★ **Trend Assassin** — ride trend birth, exit when the crowd arrives (second volume spike) | **Inspiration only.** Its exit logic (crowd-arrival) is not implemented as a standalone agent in v0; the Breakout agent covers trend-birth entries. Full port is a v1 candidate. |
| ★ **Liquidity Predator** — JIT concentrated liquidity on 3x volume spikes | **Not ported.** Needs a live DEX pool feed (Raydium) and real LP mechanics; cannot be backtested honestly on CEX klines. v1 candidate with a DEX feed. |
| ★ **Echo Frequency (EFP)** — FFT spectral cycle + normalised shape matching | **Ported** as `EchoAgent` (signal producer). FFT dominant cycle (period 8–32 bars) + 16-bar shape match (corr > 0.85, >1% follow-through), both must agree. |
| ◐ Alpha Echo Strike | **Not a standalone agent** — Echo's signals are published on the INTEL_BUS for other agents to consume, which is the producer-consumer pair in embryo. |
| ◐ Cluster Arb (flash-loan bursts) | **Not ported as execution.** Paired conceptually with Bellman (atomic executor for a proven cycle), but no execution path exists until Bellman proves a survival rate. |
| ◐ God Candle (on-chain pump + sentiment fusion) | **Not ported.** Needs on-chain data; no feed in v0. |
| ◐ HFLA CLOB lag-scalper / Grind-Shift / LMR / MGSA | **Mechanisms banked, not ported as agents.** Lead-lag divergence is the Lag Scalper's mechanism (see below); LMR's mean-reversion spirit lives in the RSI/Bollinger agents. |
| **INTEL_BUS** — shared signal bus | **Ported** as `intel_bus.py`. Every signal is published; FOMO reads breadth; Echo publishes for consumers. |
| **Phoenix (S18)** — recovery & capital defense | **Ported** as the supervisor (restart/bench) + Phoenix hibernate: equity 3% below peak → no new entries for 24 bars. |
| Ouroboros / Swarm Vault (S21) | **Not ported.** Recursive evolution from winners is a v1 idea; v0 allocates by proven expectancy only. |
| MSA / MSA stat arb | **Not a standalone agent.** The z-score pairs idea is banked; no correlated-pair universe is traded in v0 (single-asset agents). |

### OpenAgora — the swarm-training home
| Idea | Status in v0 |
|---|---|
| **Q-Learning Training Strategy** (`training_strategy.py`) — RL layer, epsilon-greedy, Bellman update, Q-table persists | **Ported and rebuilt** as `QLearningAgent`. Fixes: reward is expectancy-normalised PnL `clip(pnl/risk, -1, 1)`, NOT binary +1/-1; next_state is the REAL state at exit (original set next_state = state). Trains on the first 70% of bars, frozen (epsilon 0.02, no learning) on the last 30% — reported numbers are the frozen test-split numbers. |
| **Meta Strategy Selector** (`meta_strategy.py`) — weighted draw from win-rate weights, asset rotation cap | **Ported** as `selector.py`: Bayesian score `(2+wins)/(4+trades)`, rotation cap (never the same asset 3x in a row), 80% of capital to top 3 — but only proven winners (n>=30, expectancy>0) get anything, enforced by `ledger.allocate`. |
| Breakout (20-candle, confirmed) | **Ported** as `BreakoutAgent`, completed: original was signal-only with no exits; v0 adds TP 3% / SL 1.5% + MYTHOS trend-regime gate. |
| RSI Reversal | **Covered** by the UpsideOnly RSI agent (Wilder's RSI + ATR exits, the stronger implementation). |

### MetaTrader — 14 CEX strategies + memory
| Idea | Status in v0 |
|---|---|
| **TradeMemory** (`trade_memory.py`) — recency-decayed score (0.92/trade, 20-trade window), 0.05 weight floor, auto-blacklist at -$150, per-regime memory, confidence calibration, reflection every 10 cycles | **Ported** as `memory.py` (explicit JSON path instead of writing `.metatrader_brain.json` into the CWD). |
| Funding Rate Arb, Stat Arb (z-score), VWAP Reversion, CVD divergence, Momentum Breakout, Liquidity Sweep, OI Spike, Liquidation Cascade, Sentiment Confluence, Bollinger Squeeze, Token Unlock, Cross-Exchange Arb, Grid (regime-gated) | **Banked as the strategy bench, not ported as agents.** Most need feeds v0 doesn't have (funding rates, OI, liquidation zones, unlock calendar, CVD, order-book walls). The regime-gated grid idea lives on in the MYTHOS regime gates. Funding arb and stat arb are the top v1 candidates once feeds exist. |

### OpenTrade — Polymarket / Kalshi
| Idea | Status in v0 |
|---|---|
| Yes/No Arb, Dump & Hedge, Yield Farming, Maker Rebate, Copy Trading, Grid, Flash-Loan Arb, Grind, Momentum, Mean Reversion, Ascetix Mode (4-signal confluence) | **Dump & Hedge: PORTED** (15m spot track, see "Dump & Hedge" section above — Kevin's favourite, the only positive-expectancy port). **Ascetix: ADAPTED as NEW AscetixSpot** (spot 1x proxies, benched — no edge). The rest: **not ported.** Prediction markets are a different venue with different data (Polymarket CLOB/Gamma, Kalshi). v0 trades crypto spot on Binance.US klines only. Ascetix's confluence idea (3-of-4 signals must agree) is the direct ancestor of FOMO's 3-of-4 voting. |
| **Oracle Prime** (Kalshi weather edge, NWS forecast vs market price, quarter-Kelly) | **Not ported.** Needs Kalshi + NWS feeds. Most differentiated edge in the recovery — top v1 candidate. |
| MetaStrategyRouter (Bayesian, 80/20 top-3) | **Ported** in `selector.py` (see OpenAgora row). |
| NewsSentimentEngine, StrategyForge, CorrelationEngine | **Not ported.** Sentiment/codegen engines need an LLM + RSS feeds; v0 has no LLM calls. |

### MYTHOS-PRIME — the cleanest specifications
| Idea | Status in v0 |
|---|---|
| **RegimeDetector + edge regimes** — a strategy only fires inside its edge regime (trend vs sideways vs volatile) | **Ported** as the regime gate in `indicators.regime()` + agents: RSI/Bollinger fire in SIDEWAYS only, Breakout in TREND only. Every signal carries entry/SL/TP, as in MYTHOS. |
| MeanReversion_BB, Momentum_Breakout, Supertrend, MACD Cross, Golden Cross, Stochastic, Volatility Expansion, Fibonacci Pullback, Ichimoku, Volume-Price Delta | **Not ported as separate agents.** They are the v1 bench — the cleanest specs to port next, since each already declares its regime + exits. Volume-Price Delta's volume-spike trigger is the closest cousin of FOMO's volume vote. |

### UpsideOnly-AgoraPrime
| Idea | Status in v0 |
|---|---|
| **Double-gate: min confidence 0.60 AND min R:R 1.5 on every signal** | **Ported and enforced in the engine** on ALL agents (not just RSI). Signals failing either gate are dropped and counted. |
| RSI Mean Reversion (Wilder's RSI, ATR exits) | **Ported** as `RsiMeanReversionAgent`, with the fix below. |
| Bollinger Fade (TP at the mid-band) | **Ported** as `BollingerFadeAgent`. |
| VWAP Reversion | **Not ported** (equities/session-VWAP concept; v0 is 24/7 crypto). |

### BELLMAN-SCANNER — the cycle hunter (Kevin: "you forgot Belmont scanner" — not forgotten)
| Idea | Status in v0 |
|---|---|
| **Bellman-Ford negative-cycle arb** — token graph, edge weight `-log(rate)`, negative cycle = profitable multi-hop loop (SOL→BONK→USDC→SOL), 30 bps slippage/hop + 10 bps flash-loan fee, EXECUTE only if net > $1 on a $50k loan | **Ported as a paper-scan module** (`bellman.py` + `bellman_scan.py`). No execution path. Scan over 1,044 real 1h snapshots found **0 cycles** (consistent CEX cross-rates, as expected — a scanner that found profit there would be lying). Detection is proven on a planted 2% mispricing: cycle found, net **+$500.00**, verdict EXECUTE. Survival rate on real data: **0%** — no execution path earned until a live DEX quote feed proves otherwise. |
| USDT mint placeholder | **FIXED**: `Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB` (was `Es9vMFfGZg9oDqP6Z3D4b5s5z6c7d8e9f0g1h2i3j4k5l6m7n8o9p`). JTO was also fabricated — fixed to `jtojtomepa8beP8AuQZ4eXt5FriJwfFMwQx2v2fN6CF`. Both unit-tested. |
| Quote-freshness caveat | **Kept in the open**: detection is only as good as quote freshness; prices move while the graph is fetched. |

### PolygonSniper / apollo-x-engine
| Idea | Status in v0 |
|---|---|
| New-pair sniping (QuickSwap PairCreated, 500ms buy, TP +50% / SL -20%) | **Not ported.** Meme-coin sniping with no rug-check is high-risk by nature; no live chain feed in v0. |
| apollo-x-engine (OODA/PDCA/RL loops) | **Not ported.** Generic agent-loop framework, no alpha. The supervisor + Q-learning cover the loop need in v0. |

### Gravia-Class Lag Scalper (Polymarket dashboard)
| Idea | Status in v0 |
|---|---|
| Lead-lag divergence (lead moves, lag hasn't repriced), 4¢/8¢ thresholds, 90s expiry | **Mechanism banked.** Not a live agent (Polymarket venue, expired pair templates, hand-entered correlation). The mechanism ports to any correlated-pair venue in v1. |
| Kelly sizing | **FIXED, not copied.** See "Faults fixed". |

## Faults fixed in v0 (do NOT reintroduce)
1. **Lambda-`__init__` returning a tuple** — 9 Gravia agent types died on startup (`TypeError: __init__() should return None, not 'tuple'`); `asyncio.gather` with no `return_exceptions` let one crash kill all 910 agents after 28 seconds. Fixed by: plain `__init__` in every agent + supervisor pattern (restart up to 3x, then bench, log, keep trading). Proven by the smoke test's deliberate crash agent.
2. **Fake P&L engines** — Gravia Strike v2 `execute_trade_sim` filled 76% at random and always booked positive profit; `fetch_price_sim` was a random walk; `rug_check` was random rolls. None of it is in v0. Prices are real Binance.US history; fills are real entry/exit prices; fees + slippage always subtracted; the ledger rejects non-positive/non-finite prices.
3. **Kelly sizing algebraically $0** — old formula `(b·p − q)/b` with `b=(1−p)/p` equals 0 for all inputs. Fixed: `f* = p − (1−p)·m/(1−m)`, clamped to quarter-Kelly. Unit-tested (old == 0 for all inputs, new == 0.20 for p=0.60, m=0.50). Not used for sizing in v0 (fixed $1,000 notional keeps PnLs comparable).
4. **MEV/Jito frontrunning** — does not transfer to Solana (no public mempool). Not ported, anywhere.
5. **UpsideOnly RSI R:R gate unsatisfiable** — original TP 2.0×ATR / SL 1.5×ATR gives R:R = 1.33 always, below its own 1.5 gate, so the original agent could never fire (verified: 0 trades in the first 4h run). Fixed to TP 2.5×ATR (R:R 1.67).
6. **Bellman USDT/JTO mints** — both were fabricated placeholders; fixed to the real mainnet mints (above).
7. **Q-learning reward + next-state bugs** — binary +1/-1 rewards and `next_state = state` in the original. Fixed: expectancy-normalised reward, real exit-state.
8. **MYTHOS regime gate compared two 50-bar means ONE bar apart** — a 50-bar SMA moves ~0.02%/bar, so the 0.5% trend threshold almost never fired: 99.9% of 1h bars read SIDEWAYS, which silently benched BREAKOUT and ECHO in the first 1h run (both 0 trades). Fixed: compare the 50-bar SMA now vs 50 bars ago (a real 50-bar slope). Distribution is now ~40% up / ~40% down / ~15% sideways. Run-2 numbers for RSI/Bollinger/BREAKOUT/ECHO are all void (they traded, or didn't trade, under the broken gate); run 3 supersedes them — including RSI, whose run-2 positive (+$3.54) flipped to −$0.54 with a real gate.
9. **Phoenix hibernate froze the swarm permanently** — once equity sat >$300 below peak, the rule re-hibernated every 24 bars forever: 993 hibernations froze bars ~16,590–25,040 of the first 1h run, so the swarm could never trade back. Fixed: after 3 consecutive hibernations the peak resets to current equity (loss accepted as the new baseline) and trading resumes. Drawdown is still reported honestly.
10. **Ascetix cooldown was documented but not enforced** — the first experiments run let ASCETIX_SPOT fire every bar (4,875 trades, churn). Fixed: `simulate()` now enforces `cooldown_bars` between entries (15 bars for Ascetix).

## Deliberately NOT ported (and why)
- **Random price / random profit / random rug-check** — fabrication, not strategy.
- **MEV/Jito** — doesn't work on Solana.
- **Liquidity Predator, God Candle, Oracle Prime, funding arb, OI/liquidation feeds** — need live feeds v0 doesn't have (DEX pools, on-chain, Kalshi/NWS, funding/OI). They are the v1 bench, not silently dropped. (Ascetix was adapted as NEW AscetixSpot and benched — see above.)
- **Polymarket/Kalshi strategies** — different venue, different data. v0 is crypto spot on Binance.US klines.
- **PolygonSniper** — no rug-check; high-risk by nature.
- **Ouroboros evolution, StrategyForge codegen** — need proven winners + an LLM first. v0 has neither yet.
- **Any live execution, any API key, any real money** — paper only, by design.

## What "magical / legendary" means here
Not one bot's mythic packaging. It's the assembly: every one of Kevin's
bots contributed something real — a brain, a gate, a memory, a router, a
hunter — and the dishonest parts (random fills, fake win rates, broken
Kelly, placeholder mints) were cut out instead of copied. The swarm is
the legend; the ledger is the proof. Right now the ledger says the
swarm is unproven and unfunded. That is the honest starting point, and
the only one a legendary build can stand on.

"""
Swarm trading bot v0 — PAPER / SIMULATION ONLY.
LIVE_MODE = False everywhere. No API keys, no exchange credentials,
no live orders. Any code path that would place a live order is disabled
and logged (see execution.py guard in backtest.py).

Rules (from the design doc):
  1. Every fill is wired to a REAL entry price and a REAL exit price
     (real Binance.US 4h history, data/*.json). No random P&L.
  2. Score on EXPECTANCY, not win rate.
  3. Fees + slippage on every trade.
  4. One agent crashing kills that agent only — supervisor pattern.
  5. Capital flows to proven winners only (n >= 30, expectancy > 0).
"""
from __future__ import annotations

LIVE_MODE = False  # NEVER set True in v0. There is no live execution path.

# Paper account
PAPER_CAPITAL = 10_000.0      # dollars
NOTIONAL_PER_TRADE = 1_000.0  # fixed notional per trade (comparable PnL)
FEE_BPS_PER_SIDE = 10.0       # 0.10% taker fee per side
SLIPPAGE_BPS = 5.0            # 5 bps slippage on notional

# Backtest universe — real Binance.US klines, 2024-01-01 -> 2026-11-09.
# 1h bars are the main run (more samples than 4h; 4h data is kept in
# data/*_4h.json and the 4h run is logged in backtest_run_4h.log).
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INTERVAL = "1h"
DATA_DIR = "data"
WARMUP_BARS = 50              # bars needed before any agent may fire
MAX_HOLD_BARS = 100           # force-exit a stale position after 100 bars
TRAIN_FRACTION = 0.70         # Q-learning trains on first 70%, tested on last 30%

# FOMO/PANIC (design doc S28): TP 2.5%, SL 1%, 10-bar time stop,
# 3-loss circuit breaker, $300 loss limit (per agent, rolling 6 bars).
FOMO_TP = 0.025
FOMO_SL = 0.010
FOMO_TIME_STOP_BARS = 10
FOMO_MAX_CONSEC_LOSSES = 3
FOMO_LOSS_LIMIT = 300.0

# Kraken Funded challenge rules (paper target for v0):
# make +12%, never drop 3% (max drawdown from peak equity).
KRAKEN_TARGET_PCT = 0.12
KRAKEN_MAX_DD_PCT = 0.03
KRAKEN_TARGET_DOLLARS = PAPER_CAPITAL * KRAKEN_TARGET_PCT    # $1,200
KRAKEN_MAX_DD_DOLLARS = PAPER_CAPITAL * KRAKEN_MAX_DD_PCT    # $300

# Phoenix capital defense: if swarm equity falls 3% from its peak,
# hibernate (no new entries) for 24 bars, then resume.
PHOENIX_HIBERNATE_BARS = 24

# Ghost stealth execution (modelled, see backtest.py): high-confidence
# fills (>=0.80) are modelled at 2 bps slippage instead of 5 bps —
# the literal 5-wallet randomised splitting is NOT simulated; the
# effect (smaller footprint, better fills) is approximated and disclosed.
GHOST_CONFIDENCE = 0.80
GHOST_SLIPPAGE_BPS = 2.0

# UpsideOnly double-gate, enforced on EVERY agent in the engine:
# min confidence 0.60 AND min R:R 1.5 — signals failing either are dropped.
MIN_CONFIDENCE = 0.60
MIN_RR = 1.5

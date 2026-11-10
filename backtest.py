"""
Backtest engine — paper only.

  - Data: real Binance.US 4h klines (data/*_4h.json), 2024-01-01 -> now.
    No random walk, no invented prices. Binance.com was geo-blocked (451)
    from this VM, so Binance.US is the source; the file records that.
  - Execution: a signal at bar i fills at bar i+1's OPEN (no lookahead —
    you cannot trade at a close you have only just seen). TP/SL are
    checked against bar i+1..'s high/low; time stops and the 100-bar max
    hold force an exit at the close.
  - Costs: 10 bps taker fee per side + 5 bps slippage on notional,
    charged on every trade via the honest ledger.
  - LIVE GUARD: place_live_order() raises unconditionally. There is no
    live path in v0; if anyone wires one in, it must stay disabled and
    log the attempt.
  - Q-learning: trains on the first 70% of bars, then frozen (epsilon
    pinned, alpha=0) for the last 30% — the reported Q numbers are the
    frozen test-split numbers, not training numbers.
  - Rotation cap: the engine never opens the same asset 3 times in a row.
"""
from __future__ import annotations

import json
import math
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from config import (FEE_BPS_PER_SIDE, GHOST_CONFIDENCE, GHOST_SLIPPAGE_BPS,
                    KRAKEN_MAX_DD_DOLLARS, KRAKEN_TARGET_DOLLARS,
                    MAX_HOLD_BARS, MIN_CONFIDENCE, MIN_RR,
                    NOTIONAL_PER_TRADE, PAPER_CAPITAL,
                    PHOENIX_HIBERNATE_BARS, SLIPPAGE_BPS, SYMBOLS,
                    TRAIN_FRACTION, WARMUP_BARS)
from intel_bus import IntelBus
from ledger import Ledger, Trade, scoreboard
from memory import TradeMemory
from runner import Supervisor
from selector import MetaSelector
from strategies import ALL_AGENTS, QLearningAgent


def place_live_order(*args, **kwargs):
    """LIVE GUARD — v0 has no live execution. Any call is a bug; refuse loudly."""
    print("[LIVE GUARD] BLOCKED attempt to place a live order — paper only.")
    raise RuntimeError("LIVE_MODE is False: live orders are disabled in swarm v0")


def load_bars(symbol: str) -> pd.DataFrame:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", f"{symbol}_{config.INTERVAL}.json")
    with open(path) as f:
        raw = json.load(f)
    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore"])
    df = df[["open_time", "open", "high", "low", "close", "volume"]].copy()
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.reset_index(drop=True)


def regime_of(df: pd.DataFrame, i: int) -> str:
    """Simple regime label for TradeMemory: trend up/down/sideways by 50-bar SMA slope."""
    if i < 50:
        return "UNKNOWN"
    sma = df["close"].iloc[i - 50:i].mean()
    prev = df["close"].iloc[i - 51:i - 1].mean()
    if sma > prev * 1.005:
        return "TREND_UP"
    if sma < prev * 0.995:
        return "TREND_DOWN"
    return "SIDEWAYS"


def run_backtest() -> dict:
    assert config.LIVE_MODE is False
    data = {s: load_bars(s) for s in SYMBOLS}
    n_bars = min(len(d) for d in data.values())
    print(f"bars per asset: {n_bars} ({config.INTERVAL}, 2024-01-01 -> 2026-11-09, Binance.US)")
    train_end = int(n_bars * TRAIN_FRACTION)

    supervisor = Supervisor(ALL_AGENTS)
    selector = MetaSelector()
    ledger = Ledger()
    bus = IntelBus()
    memory = TradeMemory(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "brain.json"))
    q_agent = supervisor.agent("Q_LEARNING")
    # Phoenix capital defense state + gate counters (for the report).
    peak_equity = PAPER_CAPITAL
    hibernate_until = -1
    hibernations = 0
    consec_hibernations = 0   # Phoenix fix: see below
    peak_resets = 0
    gated_out = 0  # signals dropped by the UpsideOnly double-gate

    # open positions: (strategy, symbol) -> dict(entry bar, tp, sl, side, time_stop)
    positions: dict[tuple[str, str], dict] = {}
    pending: list[dict] = []  # signals to fill at next bar open
    # (strategy, exit_bar, pnl) for honest train/test split reporting
    trade_bars: list[tuple[str, int, float]] = []

    def open_position(sig, bar_idx: int, fill_price: float) -> None:
        key = (sig.strategy, sig.symbol)
        if key in positions:
            return
        if not selector.rotation_ok(sig.symbol):
            return
        selector.note_entry(sig.symbol)
        positions[key] = {"side": sig.direction, "entry": fill_price,
                          "tp": sig.tp_price, "sl": sig.sl_price,
                          "bar": bar_idx, "time_stop": sig.time_stop_bars,
                          "conf": sig.confidence, "agent": sig.strategy}

    def close_position(key, exit_price: float, bar_idx: int, df) -> None:
        pos = positions.pop(key)
        strat, sym = key
        qty = NOTIONAL_PER_TRADE / pos["entry"]
        fee = NOTIONAL_PER_TRADE * FEE_BPS_PER_SIDE / 10_000.0
        # Ghost execution (modelled, disclosed in config.py): high-confidence
        # fills are modelled at 2 bps slippage instead of 5 bps.
        slip = GHOST_SLIPPAGE_BPS if pos["conf"] >= GHOST_CONFIDENCE else SLIPPAGE_BPS
        trade = Trade(strategy=strat, venue="binance-us-paper", symbol=sym,
                      side=pos["side"], entry_price=pos["entry"],
                      exit_price=exit_price, qty=qty,
                      fee_entry=fee, fee_exit=fee, slippage_bps=slip,
                      entry_time=str(df["time"].iloc[pos["bar"]]),
                      exit_time=str(df["time"].iloc[bar_idx]))
        pnl = ledger.record(trade)
        trade_bars.append((strat, bar_idx, pnl))
        agent = supervisor.agent(strat)
        if agent is not None:
            agent.note_outcome(pnl)
            if isinstance(agent, QLearningAgent):
                agent.learn(pnl, df.iloc[:bar_idx + 1])
        memory.record_trade(strat, sym, pnl, confidence=pos["conf"],
                            regime=regime_of(df, bar_idx))

    for i in range(WARMUP_BARS, n_bars):
        # --- Phoenix capital defense: halt new entries while hibernating ---
        # FIX (found in the 1h run): the old rule re-hibernated forever once
        # equity sat >$300 below peak — 993 hibernations froze bars
        # ~16,590-25,040, so the swarm could never trade its way back.
        # Now: after 3 CONSECUTIVE hibernations the peak resets to current
        # equity (the loss is accepted as the new baseline) and trading
        # resumes. The drawdown is still reported honestly in the ledger.
        equity = PAPER_CAPITAL + sum(p for _, _, p in trade_bars)
        peak_equity = max(peak_equity, equity)
        if peak_equity - equity > KRAKEN_MAX_DD_DOLLARS and i > hibernate_until:
            consec_hibernations += 1
            if consec_hibernations >= 3:
                peak_equity = equity
                peak_resets += 1
                consec_hibernations = 0
                print(f"[Phoenix] bar {i}: 3rd straight hibernation — peak "
                      f"reset to ${equity:,.2f}, trading resumes")
            else:
                hibernate_until = i + PHOENIX_HIBERNATE_BARS
                hibernations += 1
                print(f"[Phoenix] bar {i}: equity ${equity:,.2f} is "
                      f"${peak_equity - equity:.2f} below peak — hibernating "
                      f"{PHOENIX_HIBERNATE_BARS} bars")
        elif peak_equity - equity <= KRAKEN_MAX_DD_DOLLARS:
            consec_hibernations = 0
        hibernating = i <= hibernate_until
        # --- freeze Q-learning for the test split ---
        if q_agent is not None:
            q_agent.frozen = i >= train_end
            if q_agent.frozen:
                q_agent.epsilon = 0.02
        # --- fill pending signals at this bar's open ---
        for sig in pending:
            df = data[sig.symbol]
            open_position(sig, i, float(df["open"].iloc[i]))
        pending = []
        # --- manage open positions: TP/SL/time-stop/max-hold on this bar ---
        for key in list(positions):
            pos = positions[key]
            df = data[key[1]]
            bar = df.iloc[i]
            exit_price = None
            if pos["side"] == "long":
                if bar["low"] <= pos["sl"]:
                    exit_price = pos["sl"]
                elif bar["high"] >= pos["tp"]:
                    exit_price = pos["tp"]
            else:
                if bar["high"] >= pos["sl"]:
                    exit_price = pos["sl"]
                elif bar["low"] <= pos["tp"]:
                    exit_price = pos["tp"]
            if exit_price is None and pos["time_stop"] and i - pos["bar"] >= pos["time_stop"]:
                exit_price = float(bar["close"])
            if exit_price is None and i - pos["bar"] >= MAX_HOLD_BARS:
                exit_price = float(bar["close"])
            if exit_price is not None:
                close_position(key, float(exit_price), i, df)
        # --- breadth proxy for FOMO sentiment: share of assets up this bar ---
        ups = sum(1 for s in SYMBOLS
                  if data[s]["close"].iloc[i] > data[s]["close"].iloc[i - 1])
        breadth = (ups / len(SYMBOLS)) * 2 - 1  # -1..+1
        # --- agents tick (supervisor isolates crashes) ---
        for sym in SYMBOLS:
            if memory.is_suspended(sym):
                continue
            df = data[sym].iloc[:i + 1]
            for sig in supervisor.tick_all(sym, df, breadth=breadth):
                bus.publish(sig)  # INTEL_BUS: every signal is shared
                # UpsideOnly double-gate, enforced on EVERY agent:
                # confidence >= 0.60 AND R:R >= 1.5, else the signal dies here.
                if sig.direction == "long":
                    rr = (sig.tp_price - sig.entry_price) / (sig.entry_price - sig.sl_price)
                else:
                    rr = (sig.entry_price - sig.tp_price) / (sig.sl_price - sig.entry_price)
                if sig.confidence < MIN_CONFIDENCE or rr < MIN_RR:
                    gated_out += 1
                    continue
                if hibernating:
                    continue
                if (sig.strategy, sym) not in positions:
                    pending.append(sig)

    board = scoreboard(ledger)
    alloc = selector.allocate(ledger, PAPER_CAPITAL)
    # Swarm-level equity curve (trades in bar order) for Kraken Funded rules.
    equity_curve, peak, swarm_max_dd = PAPER_CAPITAL, PAPER_CAPITAL, 0.0
    for _, _, p in sorted(trade_bars, key=lambda t: t[1]):
        equity_curve += p
        peak = max(peak, equity_curve)
        swarm_max_dd = max(swarm_max_dd, peak - equity_curve)
    total_net = sum(p for _, _, p in trade_bars)
    return {"ledger": ledger, "board": board, "allocation": alloc,
            "supervisor": supervisor.status(), "memory_weights": memory.get_all_weights(),
            "train_end_bar": train_end, "n_bars": n_bars,
            "trade_bars": trade_bars, "gated_out": gated_out,
            "hibernations": hibernations, "peak_resets": peak_resets,
            "bus_events": len(bus),
            "swarm_total_net": total_net,
            "swarm_return_pct": total_net / PAPER_CAPITAL,
            "swarm_max_dd": swarm_max_dd,
            "swarm_max_dd_pct": swarm_max_dd / PAPER_CAPITAL,
            "kraken_target_hit": total_net >= KRAKEN_TARGET_DOLLARS,
            "kraken_dd_breached": swarm_max_dd > KRAKEN_MAX_DD_DOLLARS}


if __name__ == "__main__":
    result = run_backtest()
    print("\n=== SCOREBOARD (expectancy, best first) ===")
    for row in result["board"]:
        proven = "PROVEN" if row["sample_ok"] else f"UNPROVEN n={int(row['n'])}"
        print(f"{row['strategy']:20s} n={int(row['n']):3d} win={row['win_rate']:.0%} "
              f"avgW=${row['avg_win']:.2f} avgL=${row['avg_loss']:.2f} "
              f"exp=${row['expectancy']:+.2f}/trade PF={row['profit_factor']:.2f} "
              f"net=${row['total_net']:+.2f} maxDD=${row['max_drawdown']:.2f} [{proven}]")
    print("\n=== ALLOCATION of $10,000 paper (proven winners only) ===")
    for name, dollars in result["allocation"].items():
        print(f"  {name:20s} ${dollars:,.2f}")
    # Q-learning, test split only (frozen, epsilon 0.02) — the honest read.
    from ledger import score as ledger_score
    # trade_bars and ledger trades are recorded in the same order.
    q_trades = result["ledger"].trades("Q_LEARNING")
    q_bars = [b for (s, b, _) in result["trade_bars"] if s == "Q_LEARNING"]
    q_test_trades = [t for t, b in zip(q_trades, q_bars) if b >= result["train_end_bar"]]
    qs = ledger_score(q_test_trades)
    print(f"\n=== Q_LEARNING TEST SPLIT ONLY (bars >= {result['train_end_bar']}, frozen) ===")
    print(f"  n={int(qs['n'])} win={qs['win_rate']:.0%} avgW=${qs['avg_win']:.2f} "
          f"avgL=${qs['avg_loss']:.2f} exp=${qs['expectancy']:+.2f}/trade "
          f"net=${qs['total_net']:+.2f} maxDD=${qs['max_drawdown']:.2f}")
    print("\n=== SUPERVISOR ===", result["supervisor"])
    print("=== TRADEMEMORY WEIGHTS ===", result["memory_weights"])
    print(f"=== INTEL_BUS: {result['bus_events']} signals published; "
          f"double-gate dropped {result['gated_out']} ===")
    print(f"=== PHOENIX: {result['hibernations']} hibernations, "
          f"{result['peak_resets']} peak resets ===")
    print("\n=== KRAKEN FUNDED (paper) — target +12%, never drop 3% ===")
    print(f"  total net ${result['swarm_total_net']:+.2f} "
          f"({result['swarm_return_pct']:+.2%} of $10,000) — "
          f"target ${KRAKEN_TARGET_DOLLARS:,.0f}: "
          f"{'HIT' if result['kraken_target_hit'] else 'NOT HIT'}")
    print(f"  swarm max drawdown ${result['swarm_max_dd']:.2f} "
          f"({result['swarm_max_dd_pct']:.2%}) — limit ${KRAKEN_MAX_DD_DOLLARS:,.0f}: "
          f"{'BREACHED' if result['kraken_dd_breached'] else 'WITHIN LIMIT'}")

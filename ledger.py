"""
Honest ledger + expectancy scoring engine (v0.1) — swarm bot scaffolding.

Built 2026-10-17 ahead of Kevin's strategy hunt (arrives Oct 18).

Rules enforced here, from the design doc's five honest rules:
  1. Every fill is wired to a REAL entry price and a REAL exit price.
     record() rejects any trade with missing/non-positive prices.
     No random P&L, no fake fill printer.
  2. We score on EXPECTANCY, not win rate:
     expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
  3. Fees and slippage are subtracted from every trade. No exceptions.
  4. Sample-size honesty: scores carry a `sample_ok` flag (n >= 30).
     Anything below that is marked UNPROVEN, never funded.
  5. One strategy's bad data can never corrupt another's score
     (each strategy is scored from its own trade list).

Boring code on purpose. Cleverness belongs in strategy logic.
Stdlib only — no dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

MIN_SAMPLE = 30  # trades needed before a score is treated as real


@dataclass
class Trade:
    strategy: str          # strategy name, Kevin's words
    venue: str             # e.g. "drift-perp", "raydium-spot"
    symbol: str            # e.g. "SOL-PERP"
    side: str              # "long" or "short"
    entry_price: float     # REAL fill price in
    exit_price: float      # REAL fill price out
    qty: float             # position size in base units
    fee_entry: float = 0.0
    fee_exit: float = 0.0
    slippage_bps: float = 0.0   # expected slippage, basis points on notional
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    note: str = ""


def _check_price(value: float, name: str) -> float:
    """Reject anything that isn't a real, positive, finite price."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite price, got {value!r}")
    return float(value)


def trade_pnl(t: Trade) -> float:
    """Net P&L of one trade in quote currency. Fees and slippage always out."""
    entry = _check_price(t.entry_price, "entry_price")
    exit_ = _check_price(t.exit_price, "exit_price")
    if t.side not in ("long", "short"):
        raise ValueError(f"side must be 'long' or 'short', got {t.side!r}")
    if not math.isfinite(t.qty) or t.qty <= 0:
        raise ValueError(f"qty must be positive, got {t.qty!r}")

    direction = 1.0 if t.side == "long" else -1.0
    gross = direction * (exit_ - entry) * t.qty
    notional = entry * t.qty
    slip_cost = notional * (t.slippage_bps / 10_000.0)
    fees = max(t.fee_entry, 0.0) + max(t.fee_exit, 0.0)
    return gross - fees - slip_cost


class Ledger:
    """Append-only record of fills. One bad strategy can't poison another."""

    def __init__(self) -> None:
        self._trades: List[Trade] = []

    def record(self, t: Trade) -> float:
        """Validate, store, return net P&L. Raises on dishonest fills."""
        pnl = trade_pnl(t)  # validation happens here; raises on bad data
        self._trades.append(t)
        return pnl

    def trades(self, strategy: Optional[str] = None) -> List[Trade]:
        if strategy is None:
            return list(self._trades)
        return [t for t in self._trades if t.strategy == strategy]

    def strategies(self) -> List[str]:
        seen: List[str] = []
        for t in self._trades:
            if t.strategy not in seen:
                seen.append(t.strategy)
        return seen


def score(trades: List[Trade]) -> Dict[str, float]:
    """Expectancy-first scorecard for one strategy's trade list."""
    pnls = [trade_pnl(t) for t in trades]
    n = len(pnls)
    out: Dict[str, float] = {"n": float(n)}
    if n == 0:
        out.update(
            wins=0.0, losses=0.0, win_rate=0.0, avg_win=0.0, avg_loss=0.0,
            expectancy=0.0, profit_factor=0.0, total_net=0.0,
            max_drawdown=0.0, sample_ok=0.0,
        )
        return out

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = len(wins) / n
    loss_rate = len(losses) / n
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0

    # The one number that matters. NOT win rate.
    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    # Max drawdown from the equity curve (peak-to-trough on cumulative P&L).
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    out.update(
        wins=float(len(wins)),
        losses=float(len(losses)),
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        expectancy=expectancy,
        profit_factor=profit_factor if math.isfinite(profit_factor) else -1.0,
        total_net=sum(pnls),
        max_drawdown=max_dd,
        sample_ok=1.0 if n >= MIN_SAMPLE else 0.0,
    )
    return out


def scoreboard(ledger: Ledger) -> List[Dict[str, float]]:
    """Every strategy scored on expectancy, best first. Unproven flagged."""
    rows = []
    for name in ledger.strategies():
        s = score(ledger.trades(name))
        s["strategy"] = name  # type: ignore[assignment]
        rows.append(s)
    rows.sort(key=lambda r: r["expectancy"], reverse=True)
    return rows


def allocate(scores: List[Dict[str, float]], capital: float) -> Dict[str, float]:
    """
    v0 capital allocator sketch (paper only):
    - Only strategies with expectancy > 0 AND sample_ok get capital.
    - Split proportional to expectancy. Everyone else: benched ($0).
    Returns {strategy_name: dollars}. Sums to <= capital.
    """
    eligible = [s for s in scores if s["expectancy"] > 0 and s["sample_ok"] == 1.0]
    if not eligible or capital <= 0:
        return {s["strategy"]: 0.0 for s in scores}  # type: ignore[index]
    total_exp = sum(s["expectancy"] for s in eligible)
    out: Dict[str, float] = {}
    for s in scores:
        name = s["strategy"]  # type: ignore[index]
        if s in eligible:
            out[name] = capital * (s["expectancy"] / total_exp)
        else:
            out[name] = 0.0
    return out


def describe(s: Dict[str, float]) -> str:
    """One-line human read of a scorecard. For the chat, not the machine."""
    name = s.get("strategy", "?")
    proven = "PROVEN" if s["sample_ok"] == 1.0 else f"UNPROVEN (n={int(s['n'])})"
    return (
        f"{name}: expectancy ${s['expectancy']:+.2f}/trade, "
        f"win {s['win_rate']:.0%} (avg win ${s['avg_win']:.2f} / "
        f"avg loss ${s['avg_loss']:.2f}), PF {s['profit_factor']:.2f}, "
        f"max DD ${s['max_drawdown']:.2f} [{proven}]"
    )

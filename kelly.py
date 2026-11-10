"""
Fixed Kelly sizing — the Gravia-Class Lag Scalper bug, fixed.

THE BUG (design doc): the old code computed
    b = (1-p)/p ; kelly = (b*p - q)/b
  where q = 1-p.  b*p = (1-p) = q, so kelly = (q - q)/b = 0 for ALL inputs.
  Every signal sized $0.00. Algebraically dead.

THE FIX — correct binary Kelly for a bet at market price m with true
probability p of paying $1:
    f* = p - (1-p) * m / (1-m)
  (edge = p - m; odds against = m/(1-m); f* = edge / odds).
  Clamped to [0, 0.25] (quarter-Kelly ceiling, as the original intended).

Kept as a utility + test. v0 backtest uses fixed $1,000 notional per trade
so strategy PnLs stay comparable; Kelly is NOT used for sizing in v0.
"""
from __future__ import annotations


def kelly_fraction(p: float, m: float, cap: float = 0.25) -> float:
    """Correct binary Kelly fraction. p = true win prob, m = market price."""
    if not (0.0 < p < 1.0 and 0.0 < m < 1.0):
        raise ValueError(f"p and m must be in (0,1), got p={p}, m={m}")
    f = p - (1.0 - p) * m / (1.0 - m)
    return max(0.0, min(cap, f))


def old_broken_kelly(p: float) -> float:
    """The original broken formula, kept only so the test can prove it is 0."""
    q = 1.0 - p
    b = (1.0 - p) / p
    return (b * p - q) / b

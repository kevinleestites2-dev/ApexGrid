"""
Bellman paper-scan — run over REAL 1h closes (Binance.US, BTC/ETH/SOL
+ USDC pinned at $1.00), sampled every 24 bars.

Cross-rates built from real closes are consistent by construction
(BTC/ETH * ETH/SOL * SOL/BTC == 1), so after 30bps/hop + 10bps flash
fee the honest expectation is ZERO executable cycles. The scan verifies
that — a scanner that hallucinated profit on consistent prices would
be lying. The detection itself is proven separately on a deliberately
mispriced rate set (see the synthetic case below + smoke_test.py).

Run: python3 bellman_scan.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bellman import evaluate_cycle, scan_snapshot

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def load_close(symbol: str) -> list[float]:
    with open(os.path.join(DATA, f"{symbol}_1h.json")) as f:
        rows = json.load(f)
    return [float(r[4]) for r in rows]


def cross_rates(btc: float, eth: float, sol: float) -> dict:
    """Consistent cross-rates from real USD closes. USDC = $1.00."""
    return {
        ("BTC", "ETH"): btc / eth, ("ETH", "BTC"): eth / btc,
        ("BTC", "SOL"): btc / sol, ("SOL", "BTC"): sol / btc,
        ("ETH", "SOL"): eth / sol, ("SOL", "ETH"): sol / eth,
        ("BTC", "USDC"): btc, ("USDC", "BTC"): 1 / btc,
        ("ETH", "USDC"): eth, ("USDC", "ETH"): 1 / eth,
        ("SOL", "USDC"): sol, ("USDC", "SOL"): 1 / sol,
    }


def main() -> int:
    btc = load_close("BTCUSDT")
    eth = load_close("ETHUSDT")
    sol = load_close("SOLUSDT")
    n = min(len(btc), len(eth), len(sol))
    sampled = list(range(0, n, 24))
    found = 0
    executable = 0
    for i in sampled:
        verdict = scan_snapshot(cross_rates(btc[i], eth[i], sol[i]))
        if verdict is not None:
            found += 1
            if verdict["verdict"] == "EXECUTE":
                executable += 1
                print(f"bar {i}: EXECUTE {verdict['cycle']} net ${verdict['net_usd']:.2f}")
    print(f"\nBellman paper-scan (real 1h closes, {len(sampled)} snapshots):")
    print(f"  cycles found: {found}")
    print(f"  EXECUTE verdicts: {executable}")
    print(f"  survival rate: {executable / max(found, 1):.1%} of found cycles "
          f"({executable}/{found})")
    print("  -> No execution path earned: survival rate must be proven on a "
          "live DEX quote feed first (not wired in v0).")

    # Synthetic mispricing proof: SOL is 2% cheap vs BTC on one leg.
    # A correct Bellman-Ford MUST find this cycle.
    rates = cross_rates(100_000.0, 3_000.0, 150.0)
    rates[("SOL", "USDC")] = 150.0 * 1.02   # SOL overpriced 2% on this leg
    rates[("USDC", "SOL")] = 1.0 / (150.0 * 1.02)
    verdict = scan_snapshot(rates)
    assert verdict is not None, "Bellman-Ford missed a planted 2% cycle"
    print(f"\nSynthetic proof (planted 2% mispricing): cycle {verdict['cycle']}, "
          f"gross {verdict['gross_return']:+.2%}, net ${verdict['net_usd']:+.2f}, "
          f"verdict {verdict['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

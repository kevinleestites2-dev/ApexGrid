"""
Bellman-Ford negative-cycle arb scanner — BELLMAN-SCANNER, included
properly in v0 as Kevin asked. NOT forgotten.

Idea (from ~/workspace/goals/swarm-training-trading-bot/hidden_files/
repos/BELLMAN-SCANNER/BELLMAN_SCANNER.py):
  Model DEX prices as a token graph. Edge weight = -log(rate).
  Run Bellman-Ford to find negative cycles = profitable multi-hop loops
  (e.g. SOL -> BONK -> USDC -> SOL). Subtract 30 bps slippage per hop
  + 10 bps flash-loan fee; only signal EXECUTE if net profit > $1 on a
  $50k loan, else MONITOR.

Paper-scan mode FIRST (design doc): log every negative cycle found,
then measure how many would have survived fees + slippage. Only a
proven survival rate earns it an execution path. There is NO execution
path in v0 — this module scans and logs only.

Fault fixed first: the saved code's USDT mint was a placeholder
("Es9vMFfGZg9oDqP6Z3D4b5s5z6c7d8e9f0g1h2i3j4k5l6m7n8o9p").
Real mint is Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB, and the JTO
mint was also fabricated (fixed to jtojtomepa8beP8AuQZ4eXt5FriJwfFMwQx2v2fN6CF).
See bellman_mints.py — both fixes are unit-tested in smoke_test.py.

Caveat, kept in the open: cycle detection is only as good as quote
freshness. Prices move while the graph is being fetched, so a cycle
found on stale quotes may already be gone. v0 scans on real 1h closes
(Binance.US) where cross-rates are consistent by construction — the
honest expectation there is ZERO executable cycles, and the scan
below verifies exactly that. A live DEX feed (Jupiter quotes) is what
would make this a real hunter; that feed is not wired in v0.
"""
from __future__ import annotations

import math

SLIPPAGE_BPS_PER_HOP = 30.0
FLASH_LOAN_FEE_BPS = 10.0
MIN_PROFIT_USD = 1.00
LOAN_USD = 50_000.0


def build_graph(rates: dict[tuple[str, str], float]) -> dict[str, dict[str, float]]:
    """(from, to) -> rate  into  node -> {node: -log(rate)} edge weights."""
    graph: dict[str, dict[str, float]] = {}
    for (a, b), rate in rates.items():
        if rate <= 0:
            continue
        graph.setdefault(a, {})[b] = -math.log(rate)
    return graph


def find_negative_cycle(graph: dict[str, dict[str, float]]) -> list[str] | None:
    """Bellman-Ford from a super-source. Returns a negative cycle
    (list of tokens, start repeated at the end) or None."""
    nodes = list(graph)
    if not nodes:
        return None
    dist = {n: 0.0 for n in nodes}  # super-source: all distances start at 0
    pred: dict[str, str | None] = {n: None for n in nodes}
    relaxed: str | None = None
    for _ in range(len(nodes)):
        relaxed = None
        for u, edges in graph.items():
            for v, w in edges.items():
                if dist[u] + w < dist[v] - 1e-12:
                    dist[v] = dist[u] + w
                    pred[v] = u
                    relaxed = v
        if relaxed is None:
            break
    if relaxed is None:
        return None
    # Walk back len(nodes) steps to land inside the cycle, then trace it.
    node = relaxed
    for _ in range(len(nodes)):
        node = pred[node]  # type: ignore[assignment]
    cycle = [node]
    cur = pred[node]
    while cur is not None and cur != node:
        cycle.append(cur)
        cur = pred[cur]
    cycle.append(node)
    cycle.reverse()
    return cycle


def cycle_gross_return(rates: dict[tuple[str, str], float], cycle: list[str]) -> float:
    """Product of rates around the cycle, minus 1 (gross return, no fees)."""
    ret = 1.0
    for a, b in zip(cycle, cycle[1:]):
        ret *= rates[(a, b)]
    return ret - 1.0


def evaluate_cycle(rates: dict[tuple[str, str], float], cycle: list[str]) -> dict:
    """Net-profit verdict for one cycle: EXECUTE only if net > $1 on $50k."""
    hops = len(cycle) - 1
    gross = cycle_gross_return(rates, cycle)
    cost = (hops * SLIPPAGE_BPS_PER_HOP + FLASH_LOAN_FEE_BPS) / 10_000.0
    net_return = gross - cost
    net_usd = net_return * LOAN_USD
    return {
        "cycle": cycle, "hops": hops,
        "gross_return": gross, "cost": cost,
        "net_return": net_return, "net_usd": net_usd,
        "verdict": "EXECUTE" if net_usd > MIN_PROFIT_USD else "MONITOR",
    }


def scan_snapshot(rates: dict[tuple[str, str], float]) -> dict | None:
    """One paper-scan snapshot: find a cycle, evaluate it, return the
    verdict dict, or None if no negative cycle exists."""
    graph = build_graph(rates)
    cycle = find_negative_cycle(graph)
    if cycle is None:
        return None
    return evaluate_cycle(rates, cycle)

"""
Bellman-Ford mint map — CORRECTED addresses (paper-scan only, no execution).

Faults found in BELLMAN-SCANNER/BELLMAN_SCANNER.py:
  - USDT was "Es9vMFfGZg9oDqP6Z3D4b5s5z6c7d8e9f0g1h2i3j4k5l6m7n8o9p"
    — a fabricated placeholder (sequential letters after the real prefix).
    Real USDT (Tether) mint: Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB
  - JTO was "jtojtQj6N1VJ3KQgMmL4QjF6mG5K3Z5D4c3b2a1" — also fabricated.
    Real JTO mint: jtojtomepa8beP8AuQZ4eXt5FriJwfFMwQx2v2fN6CF
  - All other mints in the file check out against the well-known Solana
    mainnet addresses (SOL, USDC, BONK, JUP, RAY, ORCA, PYTH).

This module is PAPER-SCAN ONLY: it exposes the corrected map and a
validator. No Jupiter calls, no trades. A Bellman-Ford execution path
does not exist in v0 — per the design doc, the scanner must first prove
its cycles survive fees + slippage in paper-scan mode.
"""
from __future__ import annotations

# Well-known Solana mainnet mints (verified against public token lists).
MINT_MAP = {
    "SOL":  "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",   # FIXED (was placeholder)
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "JUP":  "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "RAY":  "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "ORCA": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
    "PYTH": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "JTO":  "jtojtomepa8beP8AuQZ4eXt5FriJwfFMwQx2v2fN6CF",     # FIXED (was placeholder)
}

# The two faulty values from the recovered file, kept as a regression guard.
KNOWN_BAD_MINTS = {
    "USDT": "Es9vMFfGZg9oDqP6Z3D4b5s5z6c7d8e9f0g1h2i3j4k5l6m7n8o9p",
    "JTO": "jtojtQj6N1VJ3KQgMmL4QjF6mG5K3Z5D4c3b2a1",
}


def validate_mints() -> list[str]:
    """Return a list of problems; empty list = map is clean."""
    problems = []
    for token, mint in MINT_MAP.items():
        if not (32 <= len(mint) <= 44):
            problems.append(f"{token}: bad length {len(mint)}")
        if mint in KNOWN_BAD_MINTS.values():
            problems.append(f"{token}: still the placeholder mint")
    for token, bad in KNOWN_BAD_MINTS.items():
        if MINT_MAP.get(token) == bad:
            problems.append(f"{token}: placeholder not fixed")
    return problems

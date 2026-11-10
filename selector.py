"""
Meta Strategy Selector / MetaStrategyRouter — port of OpenAgora
meta_strategy.py + OpenTrade trade.py I2 (Bayesian router).

- Selection weights: Bayesian score (2+wins)/(4+trades) per strategy,
  blended with TradeMemory's recency-decayed weights.
- Asset rotation cap (OpenAgora v3.1): never take the same asset 3 times
  in a row — forces diversification. (Cap is 2 repeats; the 3rd
  consecutive same-asset signal is demoted below the next alternate.)
- Capital: 80% to the top 3 proven strategies, 20% to the rest — but
  ONLY strategies with expectancy > 0 AND n >= 30 (sample_ok) get any
  capital at all (ledger.allocate enforces this; the router never
  overrides it).
"""
from __future__ import annotations

from ledger import Ledger, allocate, scoreboard


class MetaSelector:
    ASSET_REPEAT_CAP = 2  # max consecutive entries on the same asset

    def __init__(self) -> None:
        self._last_asset: str | None = None
        self._repeat_count = 0

    def rotation_ok(self, asset: str) -> bool:
        """False when this asset has already been taken ASSET_REPEAT_CAP times in a row."""
        if asset == self._last_asset and self._repeat_count >= self.ASSET_REPEAT_CAP:
            return False
        return True

    def note_entry(self, asset: str) -> None:
        if asset == self._last_asset:
            self._repeat_count += 1
        else:
            self._last_asset = asset
            self._repeat_count = 1

    @staticmethod
    def bayesian_score(wins: int, trades: int) -> float:
        """(2+wins)/(4+trades) — Laplace-smoothed win rate (OpenTrade I2)."""
        return (2 + wins) / (4 + trades)

    def allocate(self, ledger: Ledger, capital: float) -> dict:
        """Capital allocation from the honest ledger scoreboard."""
        return allocate(scoreboard(ledger), capital)

    def ranked(self, ledger: Ledger) -> list[dict]:
        return scoreboard(ledger)

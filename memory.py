"""
TradeMemory — port of MetaTrader trade_memory.py (I1 in the recovery doc).

Per-strategy memory: wins/losses, total PnL, recency-decayed weighted
score (decay 0.92/trade, rolling 20-trade window), normalised allocation
weights with a 0.05 floor (never fully abandons a strategy), auto-blacklist
(suspend any pair whose cumulative loss breaches -$150), per-regime
win/loss memory with best_strategy_for_regime(), confidence calibration,
and a reflection every 10 cycles. Persists to JSON at the given path
(original wrote .metatrader_brain.json into the CWD — v0 takes an
explicit path so it never pollutes the workspace).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

DECAY = 0.92
MAX_HISTORY = 20
BLACKLIST_LOSS = -150.0
REFLECT_EVERY = 10


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TradeMemory:
    def __init__(self, path: str) -> None:
        self.path = path
        self.brain: dict = {
            "version": "1.0", "created": _now(), "cycle_count": 0,
            "strategy_stats": {}, "pair_stats": {}, "blacklist": [],
            "regime_stats": {}, "confidence_cal": {}, "lessons": [],
        }
        try:
            with open(path) as f:
                self.brain = json.load(f)
        except Exception:
            pass

    def save(self) -> None:
        with open(self.path, "w") as f:
            json.dump(self.brain, f, indent=2)

    def record_trade(self, strategy: str, pair: str, pnl: float,
                     confidence: float = 0.6, regime: str = "UNKNOWN") -> None:
        b = self.brain
        won = pnl > 0
        s = b["strategy_stats"].setdefault(strategy, {
            "wins": 0, "losses": 0, "total_pnl": 0.0,
            "weighted_score": 1.0, "history": []})
        s["wins" if won else "losses"] += 1
        s["total_pnl"] = round(s["total_pnl"] + pnl, 4)
        s["history"].append({"pnl": pnl, "ts": _now()})
        s["history"] = s["history"][-MAX_HISTORY:]
        score = 0.0
        for i, t in enumerate(reversed(s["history"])):
            score += (1.0 if t["pnl"] > 0 else -0.5) * (DECAY ** i)
        s["weighted_score"] = round(score, 4)
        p = b["pair_stats"].setdefault(pair, {"trades": 0, "total_pnl": 0.0, "streak": 0})
        p["trades"] += 1
        p["total_pnl"] = round(p["total_pnl"] + pnl, 4)
        p["streak"] = max(1, p["streak"] + 1) if won else min(-1, p["streak"] - 1)
        if p["total_pnl"] < BLACKLIST_LOSS and pair not in b["blacklist"]:
            b["blacklist"].append(pair)
            b["lessons"].append({"ts": _now(),
                "lesson": f"AUTO-SUSPENDED: {pair} | loss ${p['total_pnl']:.2f}"})
        r = b["regime_stats"].setdefault(regime, {})
        rs = r.setdefault(strategy, {"wins": 0, "losses": 0})
        rs["wins" if won else "losses"] += 1
        cal = b["confidence_cal"].setdefault(strategy, {"predicted": 0.0, "actual": 0, "total": 0})
        cal["predicted"] = round(cal["predicted"] + confidence, 4)
        cal["actual"] += 1 if won else 0
        cal["total"] += 1
        b["cycle_count"] = b.get("cycle_count", 0) + 1
        if b["cycle_count"] % REFLECT_EVERY == 0:
            self.reflect()
        self.save()

    def get_all_weights(self) -> dict:
        stats = self.brain["strategy_stats"]
        if not stats:
            return {}
        weights = {k: max(0.05, v.get("weighted_score", 1.0) + 2.0) for k, v in stats.items()}
        total = sum(weights.values())
        return {k: round(v / total, 4) for k, v in weights.items()}

    def is_suspended(self, pair: str) -> bool:
        return pair in self.brain.get("blacklist", [])

    def best_strategy_for_regime(self, regime: str) -> str | None:
        data = self.brain["regime_stats"].get(regime, {})
        best, best_rate = None, -1.0
        for strat, d in data.items():
            total = d["wins"] + d["losses"]
            if total and d["wins"] / total > best_rate:
                best, best_rate = strat, d["wins"] / total
        return best

    def reflect(self) -> str | None:
        stats = self.brain["strategy_stats"]
        if not stats:
            return None
        best = max(stats.items(), key=lambda x: x[1].get("weighted_score", 0))
        worst = min(stats.items(), key=lambda x: x[1].get("weighted_score", 0))
        lesson = (f"[REFLECTION] Best: {best[0]} (score={best[1].get('weighted_score', 0):.3f}, "
                  f"W/L={best[1]['wins']}/{best[1]['losses']}) | "
                  f"Worst: {worst[0]} (score={worst[1].get('weighted_score', 0):.3f}) | "
                  f"Suspended: {', '.join(self.brain['blacklist']) or 'none'}")
        self.brain["lessons"].append({"ts": _now(), "lesson": lesson})
        return lesson

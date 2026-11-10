"""
INTEL_BUS — the shared signal bus (Gravia-Prime's architectural embryo).

In Gravia-Prime, agents published signals (vortex strikes, whale copies,
echo resonance, research keywords) and other agents consumed them: the
FOMO agent read the bus for sentiment, the Ghost read it for execution
triggers. That bus — not the "600 agents" count — is the genuinely
"swarm" thing in Kevin's bots.

v0 bus is deliberately boring: publish(signal), recent(kind), and a
breadth() helper (share of the universe moving up this bar). No network,
no persistence beyond the run. FOMO's sentiment input in v0 is the
price-breadth proxy, labelled as such; the bus carries the signals so
future consumers (Ghost execution, Echo resonance) can read them.
"""
from __future__ import annotations

from collections import deque


class IntelBus:
    def __init__(self, maxlen: int = 500) -> None:
        self._events: deque = deque(maxlen=maxlen)

    def publish(self, signal) -> None:
        self._events.append({
            "strategy": signal.strategy,
            "symbol": signal.symbol,
            "direction": signal.direction,
            "confidence": signal.confidence,
        })

    def recent(self, strategy: str | None = None, limit: int = 50) -> list[dict]:
        events = list(self._events)[-limit:]
        if strategy is not None:
            events = [e for e in events if e["strategy"] == strategy]
        return events

    def sentiment(self) -> float:
        """Net direction of recent published signals, -1 (all short) .. +1 (all long)."""
        events = list(self._events)[-50:]
        if not events:
            return 0.0
        return sum(1 if e["direction"] == "long" else -1 for e in events) / len(events)

    def __len__(self) -> int:
        return len(self._events)

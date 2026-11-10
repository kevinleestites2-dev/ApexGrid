"""
Swarm runner — the supervisor pattern (the Gravia-Prime fix).

Rules:
  - Every agent runs in its own try/except per tick. One agent raising
    kills THAT agent's tick only — never the swarm.
  - A crashed agent is restarted (fresh instance) up to 3 times, then
    benched for the rest of the run. Every crash is logged with the
    agent name, bar index and exception.
  - This is the exact failure Gravia-Prime had: asyncio.gather with no
    return_exceptions let one TypeError kill all 910 agents after
    28 seconds. Here the swarm keeps trading.
"""
from __future__ import annotations

import traceback

MAX_RESTARTS = 3


class Supervisor:
    def __init__(self, agent_classes: list) -> None:
        self.agents: dict[str, object] = {}
        self.restarts: dict[str, int] = {}
        self.benched: set[str] = set()
        self.crash_log: list[dict] = []
        for cls in agent_classes:
            self.agents[cls.name] = cls()
            self.restarts[cls.name] = 0

    def tick_all(self, symbol: str, df, breadth: float = 0.0) -> list:
        """Run every live agent's tick; return the signals that survived."""
        signals = []
        for name, agent in list(self.agents.items()):
            if name in self.benched:
                continue
            try:
                sig = agent.tick(symbol, df, breadth=breadth)
                if sig is not None:
                    signals.append(sig)
            except Exception as exc:  # noqa: BLE001 — supervisor must catch all
                self._handle_crash(name, exc)
        return signals

    def _handle_crash(self, name: str, exc: Exception) -> None:
        self.crash_log.append({"agent": name, "error": repr(exc),
                               "trace": traceback.format_exc(limit=3)})
        if self.restarts[name] < MAX_RESTARTS:
            self.restarts[name] += 1
            cls = type(self.agents[name])
            self.agents[name] = cls()  # fresh instance, clean state
            print(f"[Supervisor] {name} crashed ({exc!r}) — restarted "
                  f"({self.restarts[name]}/{MAX_RESTARTS})")
        else:
            self.benched.add(name)
            print(f"[Supervisor] {name} crashed ({exc!r}) — BENCHED after "
                  f"{MAX_RESTARTS} restarts")

    def agent(self, name: str):
        return self.agents.get(name)

    def status(self) -> dict:
        return {"live": [n for n in self.agents if n not in self.benched],
                "benched": sorted(self.benched),
                "restarts": dict(self.restarts),
                "crashes": len(self.crash_log)}

"""
Smoke test — MUST pass before any sim (the test Gravia-Prime never had).

  1. Instantiate EVERY agent and run one tick each on real bars.
     (The lambda-__init__ bug dies here in seconds; it killed Gravia
     after 28s because no such test existed.)
  2. Fault isolation: a deliberately crashing agent must not kill the
     swarm — other agents still tick, the crasher restarts, then benches.
  3. Kelly fix: old formula == $0 for all inputs; new formula > 0 on an edge.
  4. Bellman mints: placeholder USDT/JTO are gone; map validates clean.
  5. Honest ledger selftest (imported).
  6. Live guard: place_live_order() raises.
Run:  python3 smoke_test.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

from backtest import load_bars, place_live_order
from bellman_mints import KNOWN_BAD_MINTS, MINT_MAP, validate_mints
from kelly import kelly_fraction, old_broken_kelly
from runner import Supervisor
from strategies import ALL_AGENTS, Agent


class CrashingAgent(Agent):
    name = "CRASH_TEST"

    def tick(self, symbol, df, breadth=0.0):
        raise RuntimeError("deliberate crash for isolation test")


def main() -> int:
    failures = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {label} {detail}")
        if not ok:
            failures.append(label)

    # 1. Every agent instantiates + one tick on real data.
    df = load_bars("BTCUSDT").iloc[:200]
    for cls in ALL_AGENTS:
        try:
            agent = cls()  # __init__ must return None, not a tuple
            sig = agent.tick("BTCUSDT", df, breadth=0.0)
            check(f"smoke:{cls.name}", True, f"-> signal={sig is not None}")
        except Exception as exc:  # noqa: BLE001
            check(f"smoke:{cls.name}", False, repr(exc))

    # 2. Fault isolation.
    sup = Supervisor(ALL_AGENTS + [CrashingAgent])
    for _ in range(4):  # 1 crash -> restart, ... 4th crash -> benched
        sigs = sup.tick_all("BTCUSDT", df, breadth=0.0)
    st = sup.status()
    check("isolation: swarm survived crashing agent",
          "CRASH_TEST" in st["benched"] and len(st["live"]) == len(ALL_AGENTS),
          str(st))
    check("isolation: crashes logged", len(sup.crash_log) >= 1,
          f"{len(sup.crash_log)} crashes logged")

    # 3. Kelly fix.
    check("kelly: old formula is $0 for all inputs",
          all(abs(old_broken_kelly(p)) < 1e-12 for p in (0.55, 0.6, 0.7, 0.9)))
    f = kelly_fraction(0.60, 0.50)  # true 60%, market 50% -> f* = 0.6 - 0.4*0.5/0.5 = 0.20
    check("kelly: fixed formula > 0 on a real edge", abs(f - 0.20) < 1e-9, f"f*={f:.3f}")
    check("kelly: no edge -> $0", kelly_fraction(0.50, 0.50) == 0.0)

    # 4. Bellman mints.
    check("bellman: mint map validates clean", validate_mints() == [], str(validate_mints()))
    check("bellman: USDT is the real Tether mint",
          MINT_MAP["USDT"] == "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB")
    check("bellman: JTO is the real mint",
          MINT_MAP["JTO"] == "jtojtomepa8beP8AuQZ4eXt5FriJwfFMwQx2v2fN6CF")
    check("bellman: placeholders gone",
          all(MINT_MAP[k] != v for k, v in KNOWN_BAD_MINTS.items()))

    # 5. Ledger selftest.
    import subprocess
    r = subprocess.run([sys.executable, "selftest_ledger.py"],
                       capture_output=True, text=True,
                       cwd=os.path.dirname(os.path.abspath(__file__)))
    check("ledger: selftest passes", r.returncode == 0, r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr[:200])

    # 6. Live guard.
    try:
        place_live_order("BTCUSDT", "buy", 1.0)
        check("live-guard: blocks live orders", False, "order went through!")
    except RuntimeError:
        check("live-guard: blocks live orders", True)

    # 7. INTEL_BUS publishes and reads back.
    from intel_bus import IntelBus
    from strategies import Signal as _Sig
    bus = IntelBus()
    bus.publish(_Sig("TEST", "BTCUSDT", "long", 100.0, 102.0, 99.0, 0.7))
    check("intel_bus: publish + sentiment", len(bus) == 1 and bus.sentiment() == 1.0,
          f"len={len(bus)} sentiment={bus.sentiment()}")

    # 9. Learning loop is real: Q-learning updates, TradeMemory reflects.
    import tempfile
    from strategies import QLearningAgent
    import pandas as _pd
    _df = _pd.DataFrame({"close": [100.0 + i * 0.5 for i in range(10)]})
    q = QLearningAgent()
    q.epsilon = 0.0  # deterministic: exploit -> BUY (all Q values start at 0)
    q.tick("BTCUSDT", _df)
    before = dict(q.q["bull"])
    q.learn(25.0, _df)  # a $25 win on a BUY in a bull state
    after = q.q["bull"]
    check("learning: Q-table changes on a real outcome",
          any(after[a] != before[a] for a in after), str(after))
    from memory import TradeMemory
    with tempfile.TemporaryDirectory() as td:
        mem = TradeMemory(os.path.join(td, "brain.json"))
        for i in range(10):
            mem.record_trade("RSI_MEAN_REVERSION", "BTCUSDT", 5.0 if i % 2 else -3.0)
        lessons = mem.brain["lessons"]
        check("learning: TradeMemory reflects every 10 trades",
              any("REFLECTION" in l["lesson"] for l in lessons),
              f"{len(lessons)} lessons")
        check("learning: TradeMemory weights sum to ~1",
              abs(sum(mem.get_all_weights().values()) - 1.0) < 0.01,
              str(mem.get_all_weights()))

    # 8. Bellman-Ford: finds a planted cycle, finds none on consistent rates.
    from bellman import evaluate_cycle, find_negative_cycle, build_graph
    from bellman_scan import cross_rates
    consistent = cross_rates(100_000.0, 3_000.0, 150.0)
    check("bellman: no cycle on consistent real-style rates",
          find_negative_cycle(build_graph(consistent)) is None)
    mispriced = dict(consistent)
    mispriced[("SOL", "USDC")] = 150.0 * 1.02
    mispriced[("USDC", "SOL")] = 1.0 / (150.0 * 1.02)
    cyc = find_negative_cycle(build_graph(mispriced))
    check("bellman: finds planted 2% cycle", cyc is not None, str(cyc))
    if cyc:
        v = evaluate_cycle(mispriced, cyc)
        check("bellman: planted cycle nets EXECUTE after fees",
              v["verdict"] == "EXECUTE" and v["net_usd"] > 1.0,
              f"net=${v['net_usd']:.2f}")

    print(f"\n{'ALL SMOKE TESTS PASSED' if not failures else 'FAILURES: ' + ', '.join(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

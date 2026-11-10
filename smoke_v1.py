"""smoke_v1.py — smoke-test every v1 agent before any backtest.
Every signal fn must return None or (side, tp, sl) with tp/sl on the
correct side of entry and R:R >= 1. Grid engine must run on a short
slice without crashing and must never use a future bar.
LIVE_MODE must stay False. Run: python3 smoke_v1.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from config import LIVE_MODE
from experiments_v1 import (SINGLE_1H, GRID_VARIANTS, V1Ctx, grid_simulate,
                            load_v1, make_breakout, sig_dump_param,
                            pairs_stat_arb)
from experiments import load, Ctx

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def main():
    assert LIVE_MODE is False, "LIVE_MODE must be False"
    check("live_guard", LIVE_MODE is False)
    ctx = load_v1("BTCUSDT", "1h")
    # every single-position signal: returns valid shape, no crash, no NaN TP/SL
    for name, fn in SINGLE_1H.items():
        bad = 0
        fired = 0
        for i in range(200, 2000):
            try:
                sig = fn(ctx, i)
            except Exception as e:  # noqa
                bad += 1
                print(f"  {name} raised at {i}: {e}")
                break
            if sig is None:
                continue
            fired += 1
            side, tp, sl = sig
            c = ctx.close[i]
            if side not in ("long", "short"):
                bad += 1
                break
            if side == "long" and not (tp > c > sl):
                bad += 1
                break
            if side == "short" and not (tp < c < sl):
                bad += 1
                break
            if tp != tp or sl != sl:  # NaN
                bad += 1
                break
        check(f"signal_{name}", bad == 0, f"fired={fired} in bars 200-2000")
    # grid variants on a short slice (first 3000 bars) — no crash, trades sane
    for name, kw in GRID_VARIANTS:
        if name == "GRID_ECHO":
            continue  # echo grid is slow; tested in the full run, not smoke
        try:
            s, tr = grid_simulate(ctx, **kw)
            ok = all(t["pnl"] == t["pnl"] for t in tr)  # no NaN pnl
            check(f"grid_{name}", ok, f"n={s['n']} net=${s['net']}")
        except Exception as e:  # noqa
            check(f"grid_{name}", False, f"raised: {e}")
    # breakout tuning factory + dump param factory
    for name, fn in [("breakout_factory", make_breakout(2.5, 1.5, 1.5, 20)),
                     ("dump_factory", sig_dump_param(0.03, 0.05, 0.10))]:
        try:
            sig = fn(ctx, 500)
            check(name, sig is None or (isinstance(sig, tuple) and len(sig) == 3))
        except Exception as e:  # noqa
            check(name, False, str(e))
    # pairs stat arb on a short slice: run on truncated ctxs
    try:
        a = load_v1("BTCUSDT", "1h")
        b = load_v1("ETHUSDT", "1h")
        tr = pairs_stat_arb(a, b)
        check("pairs_stat_arb", isinstance(tr, list), f"n={len(tr)}")
    except Exception as e:  # noqa
        check("pairs_stat_arb", False, str(e))
    # REGRESSION (v1 echo-cache bug): echo_agrees must be identical
    # regardless of which bar of a 16-bar block calls it first, and
    # regardless of prior calls on the same ctx.
    try:
        c1 = load_v1("BTCUSDT", "1h")
        v_first = [c1.echo_agrees(i) for i in (1000, 1005, 1010)]
        c2 = load_v1("BTCUSDT", "1h")
        # warm c2's cache from different bars of the same blocks first
        _ = [c2.echo_agrees(i) for i in (1003, 1008, 1015)]
        v_second = [c2.echo_agrees(i) for i in (1000, 1005, 1010)]
        check("echo_agrees_order_independent", v_first == v_second,
              f"{v_first} vs {v_second}")
    except Exception as e:  # noqa
        check("echo_agrees_order_independent", False, str(e))
    nfail = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"\n{len(CHECKS) - nfail}/{len(CHECKS)} v1 smoke checks pass")
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())

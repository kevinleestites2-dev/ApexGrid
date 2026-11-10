"""smoke_v3.py — smoke-test every v3 piece before any backtest.

- LIVE_MODE must stay False.
- fetch_1h_4h.py: probe a tiny live window into a temp dir (never
  overwrites data/) and check the bar shape matches the local files.
- stats3: static DD vs peak DD on synthetic trades (static <= peak,
  static = fall below STARTING balance only).
- Daily bars: resampled from 1h, sane bar count and split.
- Random baseline: deterministic per seed, simulates, long-only.
- Dump & Hedge 2026 simulator: runs, produces 2026 trades.
- Grid v3 base case MUST reproduce v2's Dynamic Grid (Kraken test
  net +$1,161, n=546, peak DD $1,007, within tolerance) — if the base
  moved, every fix comparison built on it is void.
- MR v2 factory: valid (tp > close > sl) or None, no crash.
- Short diagnostic engine: runs, short-only, labelled diagnostic.
- 4h/daily signal fns: valid long-only signals, no crash.

Run: python3 smoke_v3.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from config import LIVE_MODE
from experiments_v3 import (
    PAPER, STATIC_LIMIT, equity_dds, stats3, load_daily, make_random,
    dump_simulate, grid_dynamic_v3, run_grid_config, make_mr_v3,
    sig_turtle_short_diag, simulate_short,
)
from experiments_v2 import (
    load_v2, run_strategy, sig_trend_follow, sig_pullback,
    sig_trendrider, sig_turtle,
)
from fetch_1h_4h import fetch

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def main():
    assert LIVE_MODE is False, "LIVE_MODE must be False"
    check("live_guard", LIVE_MODE is False)
    check("static_limit", STATIC_LIMIT == 300.0, f"STATIC_LIMIT=${STATIC_LIMIT}")

    # --- fetcher probe: tiny live window, temp dir only ---
    try:
        end = int(time.time() * 1000)
        with tempfile.TemporaryDirectory() as d:
            bars = fetch("BTCUSDT", "1h", start_ms=end - 3 * 3600 * 1000,
                         end_ms=end, out_dir=d)
        ok = len(bars) >= 2 and all(
            set(b) == {"t", "open", "high", "low", "close", "volume"}
            and b["close"] > 0 for b in bars)
        check("fetcher_probe", ok, f"{len(bars)} fresh 1h bars, dict shape OK")
    except Exception as e:
        check("fetcher_probe", False, str(e))

    # --- stats3 synthetic: [+100, -250] -> static 150, peak 250 ---
    try:
        sdd, pdd, mineq = equity_dds([{"pnl": 100.0}, {"pnl": -250.0}])
        check("static_dd_math", sdd == 150.0 and pdd == 250.0 and mineq == 9850.0,
              f"staticDD=${sdd} peakDD=${pdd} minEq=${mineq}")
        sdd2, pdd2, _ = equity_dds([{"pnl": 100.0}, {"pnl": -50.0}])
        check("static_dd_never_trails", sdd2 == 0.0 and pdd2 == 50.0,
              f"win-then-dip: staticDD=${sdd2} (stays 0) peakDD=${pdd2}")
        s = stats3([{"pnl": 100.0, "ts": 1}, {"pnl": -250.0, "ts": 2}])
        check("stats3_fields", s["staticDD"] == 150.0 and s["peakDD"] == 250.0
              and s["n"] == 2, f"n={s['n']} staticDD=${s['staticDD']}")
    except Exception as e:
        check("static_dd_math", False, str(e))

    # --- data splits + daily resample ---
    try:
        ctxs = {}
        for tf in ("1h", "4h", "15m"):
            ctxs[tf] = load_v2("BTCUSDT", tf)
            check(f"split_{tf}", 0 < ctxs[tf].split < ctxs[tf].n,
                  f"split={ctxs[tf].split} n={ctxs[tf].n}")
        d = load_daily("BTCUSDT")
        check("daily_ctx", 900 < d.n < 1200 and 0 < d.split < d.n,
              f"n={d.n} split={d.split} test bars={d.n - d.split}")
        check("daily_closes_sane", bool(np.isfinite(d.close).all())
              and d.close[500] > 0, f"close[500]=${d.close[500]:.2f}")
    except Exception as e:
        check("daily_ctx", False, str(e))

    # --- random baseline: deterministic, simulates ---
    try:
        c1h = [load_v2(s, "1h") for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")]
        r1 = run_strategy(c1h, make_random(0.01, seed=7), 2.0, 1.0,
                          risk_pct=0.005, max_hold=100)
        r2 = run_strategy(c1h, make_random(0.01, seed=7), 2.0, 1.0,
                          risk_pct=0.005, max_hold=100)
        same = [t["pnl"] for t in r1["trades"]] == [t["pnl"] for t in r2["trades"]]
        check("random_deterministic", same and len(r1["trades"]) > 0,
              f"n={len(r1['trades'])} identical across runs={same}")
    except Exception as e:
        check("random_deterministic", False, str(e))

    # --- dump simulator: 2026 trades exist ---
    try:
        c15 = [load_v2(s, "15m") for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")]
        tr = dump_simulate(c15[0], 2.0, 1.0)
        n26 = sum(1 for t in tr if t["bar"] >= c15[0].split)
        check("dump_simulates", len(tr) > 0 and n26 > 0,
              f"BTC 15m n={len(tr)} 2026 n={n26}")
    except Exception as e:
        check("dump_simulates", False, str(e))

    # --- grid v3 base MUST reproduce v2's trades (net/n exact); the DD
    # methodology is DELIBERATELY stricter in v3: v2 reported
    # max(worst-asset equity DD, pooled realised-trade DD) = $1,007 in
    # test, but the true account curve sums all three assets' unrealised
    # lots bar by bar — in the 2026 bear year they all bleed together,
    # so the combined peak DD is much larger. That is a v3 correction,
    # not a reproduction failure: net and n must still match v2 exactly.
    try:
        s_train, s_test, s_all, _ = run_grid_config(c1h, 2.0, 1.0)
        ok = (abs(s_test["net"] - 1161.33) < 1 and s_test["n"] == 546
              and s_test["peakDD"] >= s_test["worstPeakDD"]
              and abs(s_train["net"] - 4558.15) < 1 and s_train["n"] == 1666)
        check("grid_base_reproduces_v2", ok,
              f"Kraken TEST net=${s_test['net']} (v2 $1,161.33) n={s_test['n']} (v2 546) | "
              f"TRAIN net=${s_train['net']} (v2 $4,558.15) n={s_train['n']} (v2 1,666) | "
              f"TEST COMBINED peakDD=${s_test['peakDD']} staticDD=${s_test['staticDD']} "
              f"vs v2 hybrid $1,007.39 / worst-asset peakDD=${s_test['worstPeakDD']} — "
              f"v2 UNDERSTATED grid DD: combined account curve is the honest number")
    except Exception as e:
        check("grid_base_reproduces_v2", False, str(e))

    # --- grid fixes each run without crashing (one asset, test split) ---
    try:
        ctx = c1h[0]
        for name, kw in (("adx15", dict(adx_gate=15.0)),
                         ("maxlot3", dict(max_lots=3)),
                         ("break", dict(break_exit=True)),
                         ("atrsp", dict(atr_spacing=True)),
                         ("ddstop", dict(max_unreal_dd=150.0))):
            s, tr, _curve = grid_dynamic_v3(ctx, 2.0, 1.0, start=ctx.split, end=ctx.n, **kw)
            assert s["n"] >= 0 and s["staticDD"] <= s["peakDD"] + 0.01
        check("grid_fixes_run", True, "adx/maxlot/break/atrspacing/ddstop all ran")
    except Exception as e:
        check("grid_fixes_run", False, str(e))

    # --- MR v2 factory: valid TP/SL ---
    try:
        ctx = c1h[0]
        bad, fired = 0, 0
        for z, sl in ((-2.0, 0.03), (-2.0, 0.05), (-1.5, 0.03)):
            fn = make_mr_v3(z, sl)
            for i in range(300, 3000):
                sig = fn(ctx, i)
                if sig is None:
                    continue
                fired += 1
                _, tp, sl_px = sig[0], sig[1], sig[2]
                if not (tp > ctx.close[i] > sl_px):
                    bad += 1
                    break
        check("mr_v2_signals", bad == 0, f"fired={fired} in bars 300-3000")
    except Exception as e:
        check("mr_v2_signals", False, str(e))

    # --- short diagnostic engine ---
    try:
        c4h = [load_v2(s, "4h") for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")]
        tr = simulate_short(c4h[0], sig_turtle_short_diag, 2.0, 1.0, risk_pct=0.002)
        check("short_diag_runs", all(t["side"] == "short" for t in tr),
              f"n={len(tr)} all short, diagnostic only")
    except Exception as e:
        check("short_diag_runs", False, str(e))

    # --- 4h/daily signals valid ---
    try:
        bad = 0
        for fn, ctx in ((sig_trend_follow, c4h[0]), (sig_pullback, c4h[0]),
                        (sig_trendrider, c4h[0]), (sig_turtle, c4h[0])):
            for i in range(300, 3000):
                sig = fn(ctx, i)
                if sig is not None and not (sig[1] > ctx.close[i] > sig[2]):
                    bad += 1
                    break
        check("tf_signals_valid", bad == 0, "trend/pullback/trendrider/turtle on 4h")
    except Exception as e:
        check("tf_signals_valid", False, str(e))

    nfail = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"\n{len(CHECKS) - nfail}/{len(CHECKS)} v3 smoke checks pass")
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())

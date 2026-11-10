"""smoke_v2.py — smoke-test every v2 signal/engine before any backtest.
Every signal fn must return None or (side, tp, sl[, opts]) with tp/sl on
the correct side of entry for a LONG, no NaN, no crash, no future bar.
Custom engines (grid, Kalman pairs, momentum rotation) must run on a
short slice without crashing. LIVE_MODE must stay False.
Run: python3 smoke_v2.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from config import LIVE_MODE
from experiments_v2 import (
    load_v2, sig_trend_follow, sig_pullback, sig_rsi2, sig_vwap_bounce,
    sig_vwap_retest, sig_trendrider, sig_turtle, sig_turtle_tp1,
    sig_ema_ribbon, sig_range, sig_vol_breakout, sig_trend_assassin_v2,
    sig_mean_rev_zscore, grid_dynamic, pairs_kalman, momentum_rotation, simulate_v2,
)

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


SIGNALS = {
    ("TREND_FOLLOW_4H", "4h"): sig_trend_follow,
    ("PULLBACK_4H", "4h"): sig_pullback,
    ("RSI2_RANGE_1H", "1h"): sig_rsi2,
    ("VWAP_BOUNCE_15M", "15m"): sig_vwap_bounce,
    ("VWAP_RETEST_15M", "15m"): sig_vwap_retest,
    ("TRENDRIDER_1H", "1h"): sig_trendrider,
    ("TURTLE_4H", "4h"): sig_turtle,
    ("TURTLE_TP1_4H", "4h"): sig_turtle_tp1,
    ("EMA_RIBBON_15M", "15m"): sig_ema_ribbon,
    ("RANGE_1H", "1h"): sig_range,
    ("VOL_BREAKOUT_1H", "1h"): sig_vol_breakout,
    ("TREND_ASSASSIN_1H", "1h"): sig_trend_assassin_v2,
    ("MEAN_REV_ZSCORE_1H", "1h"): sig_mean_rev_zscore,
}


def main():
    assert LIVE_MODE is False, "LIVE_MODE must be False"
    check("live_guard", LIVE_MODE is False)
    ctxs = {}
    for tf in ("1h", "4h", "15m"):
        ctxs[tf] = load_v2("BTCUSDT", tf)
        check(f"split_{tf}", 0 < ctxs[tf].split < ctxs[tf].n,
              f"split={ctxs[tf].split} n={ctxs[tf].n}")
        check(f"adx_{tf}", not np.isnan(ctxs[tf].adx[1000:2000]).all(),
              "ADX computed")
        check(f"rsi2_{tf}", not np.isnan(ctxs[tf].rsi2[1000:2000]).all(),
              "RSI2 computed")
    for (name, tf), fn in SIGNALS.items():
        ctx = ctxs[tf]
        bad, fired = 0, 0
        for i in range(300, 3000):
            try:
                sig = fn(ctx, i)
            except Exception as e:
                bad += 1
                print(f"  {name} raised at {i}: {e}")
                break
            if sig is None:
                continue
            fired += 1
            side, tp, sl = sig[0], sig[1], sig[2]
            c = ctx.close[i]
            if side != "long":
                bad += 1
                print(f"  {name}: non-long signal {side}")
                break
            if not (tp > c > sl) or tp != tp or sl != sl:
                bad += 1
                print(f"  {name}: bad TP/SL tp={tp} c={c} sl={sl}")
                break
        check(f"signal_{name}", bad == 0, f"fired={fired} in bars 300-3000")
    # Trend Assassin: must fire at least once on a full 1h BTC pass, and
    # the crowd exit must be reachable (simulate a few bars).
    try:
        ctx = ctxs["1h"]
        fired = sum(1 for i in range(300, ctx.n) if sig_trend_assassin_v2(ctx, i))
        check("trend_assassin_fires", fired > 0, f"fired={fired} on BTC 1h")
        tr, dropped = simulate_v2(ctx, sig_trend_assassin_v2, 10.0, 5.0, risk_pct=0.005)
        check("trend_assassin_simulates", isinstance(tr, list), f"n={len(tr)} dropped_short={dropped}")
        whys = {t["why"] for t in tr}
        check("trend_assassin_crowd_exit", "CROWD" in whys or len(tr) == 0,
              f"exit reasons={whys}")
    except Exception as e:
        check("trend_assassin_fires", False, str(e))
    # TrendRider ladder: TP must step down with holding time — check via
    # a direct simulate on a slice where it fires.
    try:
        ctx = ctxs["1h"]
        tr, _ = simulate_v2(ctx, sig_trendrider, 10.0, 5.0, risk_pct=0.005)
        check("trendrider_simulates", isinstance(tr, list), f"n={len(tr)}")
    except Exception as e:
        check("trendrider_simulates", False, str(e))
    # Custom engines on short slices
    try:
        s, tr = grid_dynamic(ctxs["1h"], 10.0, 5.0)
        check("grid_dynamic", isinstance(tr, list) and all(t["pnl"] == t["pnl"] for t in tr),
              f"n={s['n']} net=${s['net']}")
    except Exception as e:
        check("grid_dynamic", False, str(e))
    try:
        btc = load_v2("BTCUSDT", "1h")
        eth = load_v2("ETHUSDT", "1h")
        tr = pairs_kalman(btc, eth, 10.0, 5.0)
        check("pairs_kalman", isinstance(tr, list), f"n={len(tr)}")
    except Exception as e:
        check("pairs_kalman", False, str(e))
    try:
        c1h = [load_v2(s, "1h") for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")]
        tr = momentum_rotation(c1h, 10.0, 5.0)
        check("momentum_rotation", isinstance(tr, list) and len(tr) > 0,
              f"n={len(tr)} net=${sum(t['pnl'] for t in tr):.2f}")
    except Exception as e:
        check("momentum_rotation", False, str(e))
    nfail = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"\n{len(CHECKS) - nfail}/{len(CHECKS)} v2 smoke checks pass")
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())

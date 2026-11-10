"""experiments_v2_mr.py — Mean reversion backbone test (ApexGrid v2).

Kevin's call (2026-11-10): mean reversion (#14) is the BACKBONE of v2.
Test it first / hardest. Do NOT force it to pass.

Variants (pre-specified by Kevin, not tuned after seeing results):
  z-score threshold: -1.5 / -2.0 / -2.5  (price SDs below 20-period mean)
  exit: 'mean' (TP at 20-period SMA) vs 'sma5' (TP at 5-period MA)
  ADX gate: on (<25, ranging only) vs off (trade in any regime)
  timeframe: 1h vs 15m
  = 3 x 2 x 2 x 2 = 24 variants.
Common to all: BTC/ETH only, long-only spot 1x, RSI(14) < 30 at entry,
SL below recent low capped at -1.5% max distance, risk 0.25%/trade.
Same honest rules as v2: train 2024-2025, verify out-of-sample 2026,
hard mode (0.30% RT) + Kraken mode (~0.05% RT), gates exp>0, PF>1.2,
n>=100 (all-data), maxDD<=$300. A variant "passes" only on the TEST
split too (exp>0, PF>1.2, n_test>=30, test DD<=$300).

Selection-bias warning (stated up front): picking the best of 24
variants on the test split is itself a selection. A best-variant test
pass is therefore a CANDIDATE, not a proof — it would need a fresh
forward-paper period before any funding. If no variant passes even
that way, the backbone idea didn't hold.
Paper / simulation ONLY. LIVE_MODE=False. No GitHub push.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import LIVE_MODE
from experiments_v2 import load_v2, run_strategy, stats_split, ASSETS

assert LIVE_MODE is False
HERE = os.path.dirname(os.path.abspath(__file__))


def make_mean_rev(z_thresh, exit_mode, adx_gate):
    """Factory: one mean-reversion variant. adx_gate=None means no gate."""
    def fn(ctx, i):
        if i < 250 or np.isnan(ctx.sma20[i]):
            return None
        if adx_gate is not None:
            if np.isnan(ctx.adx[i]) or ctx.adx[i] >= adx_gate:
                return None
        if np.isnan(ctx.rsi[i]) or ctx.rsi[i] >= 30:
            return None
        sd20 = ctx.close[i - 20:i].std()
        if sd20 is None or np.isnan(sd20) or sd20 <= 0:
            return None
        z = (ctx.close[i] - ctx.sma20[i]) / sd20
        if z >= z_thresh:  # z_thresh is negative: need price BELOW mean
            return None
        c = ctx.close[i]
        tp = ctx.sma20[i] if exit_mode == "mean" else ctx.sma5[i]
        if np.isnan(tp) or tp <= c * 1.001:
            return None
        sl = max(ctx.low[max(0, i - 4):i + 1].min() * 0.999, c * 0.985)
        if sl >= c:
            return None
        return ("long", tp, sl, {})
    return fn


def main():
    results = {}
    ctxs = {tf: [load_v2(s, tf) for s in ASSETS] for tf in ("1h", "15m")}
    for tf in ("1h", "15m"):
        print(f"{tf}: split@{ctxs[tf][0].split}, test bars={ctxs[tf][0].n - ctxs[tf][0].split}")
    modes = {"hard": (10.0, 5.0), "kraken": (2.0, 1.0)}
    best = {}  # mode -> (tag, test stats)
    for z in (-1.5, -2.0, -2.5):
        for exit_mode in ("mean", "sma5"):
            for adx_gate in (25.0, None):
                for tf in ("1h", "15m"):
                    tag = (f"MR_z{abs(z):.1f}_{exit_mode}_"
                           f"{'adx25' if adx_gate else 'noadx'}_{tf}")
                    fn = make_mean_rev(z, exit_mode, adx_gate)
                    for mode, (fb, sb) in modes.items():
                        r = run_strategy(ctxs[tf], fn, fb, sb, risk_pct=0.0025,
                                         asset_filter=["BTCUSDT", "ETHUSDT"])
                        key = f"{tag}__{mode}"
                        results[key] = dict(train=r["train"], test=r["test"],
                                            all=r["all"])
                        t, te = r["train"], r["test"]
                        ok = (te["exp"] > 0 and te["pf"] > 1.2 and te["n"] >= 30
                              and te["maxDD"] <= 300 and r["all"]["n"] >= 100)
                        print(f"{tag:<28} {mode:<6} TRAIN n={t['n']:>4} exp=${t['exp']:>+6} "
                              f"PF={t['pf']:>5} net=${t['net']:>+8} DD=${t['maxDD']:>6} | "
                              f"TEST n={te['n']:>4} exp=${te['exp']:>+6} PF={te['pf']:>5} "
                              f"net=${te['net']:>+8} DD=${te['maxDD']:>6} "
                              f"[{'PASS-TEST' if ok else 'fail'}]")
                        if ok and (mode not in best or te["exp"] > best[mode][1]["exp"]):
                            best[mode] = (tag, te, r["all"])
    print("\nBest passing variant per mode:")
    for mode in modes:
        if mode in best:
            tag, te, al = best[mode]
            print(f"  {mode}: {tag} TEST exp=${te['exp']} PF={te['pf']} n={te['n']} "
                  f"net=${te['net']} DD=${te['maxDD']} (all n={al['n']})")
        else:
            print(f"  {mode}: NONE of the 24 variants passes the test gate.")
    json.dump(results, open(os.path.join(HERE, "experiments_v2_mr_results.json"), "w"), indent=2)
    print("\nSaved experiments_v2_mr_results.json")


if __name__ == "__main__":
    main()

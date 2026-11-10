"""experiments_v3.py — ApexGrid v3 (Claude's fixes).

Paper / simulation ONLY. LIVE_MODE=False everywhere. No live trading,
no Kraken challenge, no entry fee, no GitHub push (report first).

CRITICAL CORRECTION — drawdown measurement (verified from Kraken's own
pages, 2026-11-10, kraken.com/learn/how-do-prop-trading-firms-work and
kraken.com/gb/learn/best-crypto-prop-firms):
  Kraken Funded uses a STATIC 3% drawdown, fixed from starting balance:
  a $10,000 account's floor is $9,700 always; it does NOT trail peak
  equity. ("Kraken Funded uses a single static limit", "a fixed 3%
  drawdown floor with no separate daily limit", "the floor is $9,700".)
  v0/v1/v2 measured drawdown from PEAK equity, which is stricter than
  Kraken. v3 measures drawdown BOTH ways and reports both, but the PASS
  gate is STATIC: min equity >= $9,700 (never $300 below STARTING
  balance). Nothing is silently re-funded on static DD alone — peak DD
  is reported alongside so Kevin sees the difference.
  Caveat: one third-party roundup (daytrading.com) lists a 5% max DD
  for Kraken Funded; Kraken's own pages say 3%, so v3 gates on 3%.

v3 work, in order:
  1. fetch_1h_4h.py (separate file) — 1h/4h fetcher, tested by probe.
  2. RANDOM baseline — random entries, same exits/costs as the real
     strategies. If random loses about as much as the signals, the
     problem is exits/fees, not signals.
  3. DUMP_HEDGE_2026 — v1 tuned Dump & Hedge (T3/TP8/SL10/H96) on the
     2026 hold-out only, both cost modes. It was picked from 32 tuned
     variants — report if it holds up or collapses.
  4. GRID_FIXES — Dynamic Grid drawdown fixes, each separately and
     combined: ADX cutoff, cap on open inventory, hard exit when the
     grid breaks, spacing scaled to volatility, hard stop on unrealised
     drawdown. Goal: static DD <= $300 AND peak DD reported, PF > 1.5.
  5. MR_V2 — mean reversion v2: wide stops / time exits instead of the
     -1.5% stop that killed v2 (win rate 15-25%). SL -3%/-5%, time exit
     24h/48h, exit at mean, z -1.5/-2/-2.5, 1h and 15m.
  6. TF_4H_DAILY — best v2 strategies (Trend Following, Pullback,
     TrendRider, Turtle) on 4h and daily bars, long-only. Shorts are
     NOT Kraken-eligible (Kraken Funded is 1x spot, no leverage);
     one short diagnostic is run, clearly labelled DIAG-SHORT, never
     as a funded arm.
  7. V2_STATIC — full v2 14-strategy set re-run under STATIC drawdown
     measurement, both cost modes, train 2024-2025 vs test 2026.

Gates (v3): expectancy > 0 after costs, PF > 1.2, n >= 100 (all data),
STATIC DD <= $300 (min equity >= $9,700). Peak DD reported alongside.
Stacked swarm = only strategies passing all gates, vs Kraken +12% ($1,200).
Daily bars are resampled from the 1h klines (no daily file exists yet;
fetch_1h_4h.py can also fetch 1d to rebuild them).

Usage: python3 experiments_v3.py [section ... | all]
  Sections: random dump grid mr tf static
  Each section saves its results to experiments_v3_results.json as it
  finishes, so a partial run still leaves usable numbers.
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import LIVE_MODE, MAX_HOLD_BARS
from experiments import Ctx, load, _stats
from experiments_v1 import load_v1
from experiments_v2 import (
    ASSETS, SPLIT_MS, V2Ctx, load_v2, run_strategy, stats_split,
    sig_trend_follow, sig_pullback, sig_trendrider, sig_turtle,
    sig_turtle_tp1, sig_rsi2, sig_vwap_bounce, sig_vwap_retest,
    sig_ema_ribbon, sig_range, sig_vol_breakout, sig_trend_assassin_v2,
    sig_mean_rev_zscore, grid_dynamic, pairs_kalman, momentum_rotation,
    simulate_v2,
)
from indicators import atr, avg_volume, bollinger, rsi_wilder, sma

assert LIVE_MODE is False
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
PAPER = 10000.0
STATIC_LIMIT = 300.0  # $10,000 - $9,700 floor
RESULTS_PATH = os.path.join(HERE, "experiments_v3_results.json")


# ------------------------------------------------------------------ DD math
def equity_dds(trades):
    """Static + peak drawdown from a chronologically sorted trade list.
    Static DD = how far cumulative equity fell below STARTING balance
    ($10,000): -min(cum_pnl) if negative, else 0. Peak DD = max fall
    from the running peak. Returns (static_dd, peak_dd, min_equity)."""
    eq, peak, peak_dd, min_eq = 0.0, 0.0, 0.0, 0.0
    for t in trades:
        eq += t["pnl"]
        peak = max(peak, eq)
        peak_dd = max(peak_dd, peak - eq)
        min_eq = min(min_eq, eq)
    static_dd = -min_eq if min_eq < 0 else 0.0
    return round(static_dd, 2), round(peak_dd, 2), round(PAPER + min_eq, 2)


def stats3(trades):
    """_stats + staticDD/peakDD/minEq. Trades are sorted chronologically
    by ts when present, else by bar. _stats' own maxDD is the peak DD
    from the trade sequence; peakDD here is the same number computed on
    the chronological order (identical when already chronological)."""
    if not trades:
        return dict(n=0, win=0.0, avgW=0.0, avgL=0.0, exp=0.0, pf=0.0,
                    net=0.0, maxDD=0.0, staticDD=0.0, peakDD=0.0,
                    minEq=PAPER)
    ordered = sorted(trades, key=lambda t: t.get("ts", t.get("bar", 0)))
    s = _stats(ordered)
    static_dd, peak_dd, min_eq = equity_dds(ordered)
    s["staticDD"] = static_dd
    s["peakDD"] = peak_dd
    s["minEq"] = min_eq
    s["maxDD"] = peak_dd  # keep maxDD = peak DD for v2 comparability
    return s


def split_stats3(trades, ctxs):
    """Train/test stats3, split per trade by its own asset's split bar."""
    split_by = {sym: ctx.split for ctx, sym in zip(ctxs, ASSETS)}
    tr = [t for t in trades if t.get("bar", 0) < split_by.get(t.get("asset", ASSETS[0]), 10 ** 9)]
    te = [t for t in trades if t.get("bar", 0) >= split_by.get(t.get("asset", ASSETS[0]), 10 ** 9)]
    return stats3(tr), stats3(te), stats3(trades)


def gate_pass(s_test, s_all):
    """v3 gate: test exp>0, PF>1.2, n_test>=30, test STATIC DD<=$300,
    all-data n>=100. Peak DD is reported, not gated."""
    return (s_test["exp"] > 0 and s_test["pf"] > 1.2 and s_test["n"] >= 30
            and s_test["staticDD"] <= STATIC_LIMIT and s_all["n"] >= 100)


def _fmt3(name, mode, s_train, s_test):
    flag = "PASS" if gate_pass(s_test, {"n": s_test["n"] + s_train["n"]}) else "fail"
    print(f"{name:<26} {mode:<6} TRAIN n={s_train['n']:>5} exp=${s_train['exp']:>+6} "
          f"PF={s_train['pf']:>5} net=${s_train['net']:>+9} sDD=${s_train['staticDD']:>7} pDD=${s_train['peakDD']:>7} | "
          f"TEST n={s_test['n']:>5} exp=${s_test['exp']:>+6} PF={s_test['pf']:>5} "
          f"net=${s_test['net']:>+9} sDD=${s_test['staticDD']:>7} pDD=${s_test['peakDD']:>7} [{flag} test-gate]")


def save(results):
    json.dump(results, open(RESULTS_PATH, "w"), indent=2)


# ------------------------------------------------------------------ daily bars
def load_daily(symbol):
    """Daily ctx resampled from the 1h klines (open=first, high=max,
    low=min, close=last, volume=sum, UTC days). Base indicators are
    recomputed on the DAILY frame (not carried over from 1h)."""
    df1h = load(symbol, "1h")
    d = df1h[["t", "open", "high", "low", "close", "volume"]].copy()
    d["dt"] = pd.to_datetime(d["t"], unit="ms", utc=True)
    d = d.set_index("dt").resample("1D").agg(
        {"t": "first", "open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}).reset_index(drop=True)
    d["rsi"] = rsi_wilder(d["close"])
    d["atr"] = atr(d)
    d["sma20"] = sma(d["close"], 20)
    d["sma50"] = sma(d["close"], 50)
    d["bb_up"], d["bb_mid"], d["bb_dn"] = bollinger(d["close"])
    d["vol_avg"] = avg_volume(d["volume"])
    return V2Ctx(d)


# ============================================================ §2 random baseline
def make_random(p, tp_pct=0.02, sl_pct=0.015, seed=7):
    """Random entries: Bernoulli(p) per bar when flat, same exits as a
    typical single-position strategy (TP +2% / SL -1.5%, 100-bar hold,
    risk 0.5%/trade via simulate_v2). Deterministic per seed."""
    rng = np.random.default_rng(seed)

    def fn(ctx, i):
        if rng.random() < p:
            c = ctx.close[i]
            return ("long", c * (1 + tp_pct), c * (1 - sl_pct), {})
        return None
    return fn


def section_random(results, ctxs):
    print("\n== §2 RANDOM-ENTRY BASELINE (same exits/costs as real strategies) ==")
    # p chosen so random trades at roughly the same rate as a typical
    # signal strategy: ~0.01/bar on 1h, ~0.04/bar on 4h (4x fewer bars).
    for tf, p in (("1h", 0.01), ("4h", 0.04)):
        for mode, (fb, sb) in (("hard", (10.0, 5.0)), ("kraken", (2.0, 1.0))):
            seed_stats = []
            for seed in (7, 8, 9):
                r = run_strategy(ctxs[tf], make_random(p, seed=seed), fb, sb,
                                 risk_pct=0.005, max_hold=100)
                for t in r["trades"]:
                    t["ts"] = int(dict(zip(ASSETS, [c.ts for c in ctxs[tf]]))[t["asset"]][t["bar"]])
                tr, te, al = split_stats3(r["trades"], ctxs[tf])
                results[f"RANDOM_{tf}_s{seed}__{mode}"] = dict(train=tr, test=te, all=al)
                seed_stats.append((te, al))
                print(f"RANDOM_{tf} seed={seed} {mode:<6} TEST n={te['n']:>4} exp=${te['exp']:>+6} "
                      f"PF={te['pf']:>5} net=${te['net']:>+8} sDD=${te['staticDD']:>7} pDD=${te['peakDD']:>7} | "
                      f"ALL n={al['n']:>4} exp=${al['exp']:>+6} PF={al['pf']:>5} net=${al['net']:>+8}")
            te_mean = {k: round(sum(s[0][k] for s in seed_stats) / 3, 2)
                       for k in ("exp", "pf", "net", "staticDD", "peakDD")}
            al_mean = {k: round(sum(s[1][k] for s in seed_stats) / 3, 2)
                       for k in ("exp", "pf", "net")}
            print(f"  RANDOM_{tf} {mode} mean over 3 seeds: TEST exp=${te_mean['exp']} "
                  f"PF={te_mean['pf']} net=${te_mean['net']} sDD=${te_mean['staticDD']} "
                  f"| ALL exp=${al_mean['exp']} PF={al_mean['pf']} net=${al_mean['net']}")
            results[f"RANDOM_{tf}_mean__{mode}"] = dict(test_mean=te_mean, all_mean=al_mean)
    save(results)


# ============================================================ §3 Dump & Hedge 2026
def dump_simulate(ctx, fee_bps, slip_bps, threshold=0.03, tp_pct=0.08,
                  sl_pct=0.10, max_hold=96, size=300.0, start=100):
    """v1 tuned Dump & Hedge, fixed $300 notional, both cost modes.
    Bar low >=threshold below its open = dump; buy next bar open;
    TP +tp_pct / SL -sl_pct from signal close, SL first, TIME exit.
    Same fill semantics as experiments.simulate (hard-coded fees there,
    so this copy takes fee/slip as parameters)."""
    fee = fee_bps / 10000.0
    slip = slip_bps / 10000.0
    trades = []
    pos = None
    pending = None
    for i in range(start, ctx.n - 1):
        o, h, l, c = ctx.open[i], ctx.high[i], ctx.low[i], ctx.close[i]
        if pending is not None:
            tp, sl = pending
            fill = o * (1 + slip)
            pos = dict(entry=fill, tp=tp, sl=sl, qty=size / fill, opened=i, bar=i)
            pending = None
        if pos is not None:
            exit_px, why = None, None
            if l <= pos["sl"]:
                exit_px, why = pos["sl"] * (1 - slip), "SL"
            elif h >= pos["tp"]:
                exit_px, why = pos["tp"] * (1 - slip), "TP"
            if exit_px is None and i - pos["opened"] >= max_hold:
                exit_px, why = c * (1 - slip), "TIME"
            if exit_px is not None:
                gross = (exit_px - pos["entry"]) * pos["qty"]
                fees = (pos["entry"] * pos["qty"] + exit_px * pos["qty"]) * fee
                trades.append(dict(pnl=round(gross - fees, 2), side="long", why=why,
                                   entry=round(pos["entry"], 4), exit=round(exit_px, 4),
                                   bar=pos["bar"], ts=int(ctx.ts[pos["bar"]])))
                pos = None
        if pos is None and pending is None:
            if o > 0 and (o - l) / o >= threshold:
                pending = (c * (1 + tp_pct), c * (1 - sl_pct))
    return trades


def section_dump(results, ctxs15):
    print("\n== §3 DUMP & HEDGE 2026 HOLD-OUT (v1 tuned T3/TP8/SL10/H96, $300) ==")
    for mode, (fb, sb) in (("hard", (10.0, 5.0)), ("kraken", (2.0, 1.0))):
        all_tr, per_asset = [], {}
        for ctx, sym in zip(ctxs15, ASSETS):
            tr = dump_simulate(ctx, fb, sb)
            for t in tr:
                t["asset"] = sym
            all_tr.extend(tr)
            per_asset[sym] = tr
        tr_s, te_s, al_s = split_stats3(all_tr, ctxs15)
        results[f"DUMP_HEDGE_2026__{mode}"] = dict(train=tr_s, test=te_s, all=al_s)
        print(f"DUMP&HEDGE {mode:<6} FULL  n={al_s['n']:>4} exp=${al_s['exp']:>+6} PF={al_s['pf']:>5} "
              f"net=${al_s['net']:>+8} sDD=${al_s['staticDD']:>7} pDD=${al_s['peakDD']:>7} | "
              f"2026-ONLY n={te_s['n']:>4} exp=${te_s['exp']:>+6} PF={te_s['pf']:>5} "
              f"net=${te_s['net']:>+8} sDD=${te_s['staticDD']:>7} pDD=${te_s['peakDD']:>7} "
              f"[{'PASS-2026' if gate_pass(te_s, al_s) else 'fail'}]")
        for sym in ASSETS:
            s26 = stats3([t for t in per_asset[sym] if t["bar"] >= ctxs15[ASSETS.index(sym)].split])
            print(f"  2026 {sym}: n={s26['n']:>3} exp=${s26['exp']:>+6} PF={s26['pf']:>5} "
                  f"net=${s26['net']:>+8} sDD=${s26['staticDD']:>6} pDD=${s26['peakDD']:>6}")
            results[f"DUMP_HEDGE_2026_{sym}__{mode}"] = s26
    save(results)


# ============================================================ §4 grid fixes
def grid_dynamic_v3(ctx, fee_bps, slip_bps, spacing_pct=0.01, levels=5,
                    leg_notional=200.0, adx_gate=25.0, reset_bars=168,
                    start=250, end=None, max_lots=None, break_exit=False,
                    atr_spacing=False, max_unreal_dd=None):
    """Re-centring grid (v2 grid_dynamic) + v3 drawdown fixes.
    Fixes, each switchable so they can be tested separately:
      adx_gate   — ADX cutoff for new buys (range only); try 15/20/25.
      max_lots   — cap on open inventory (total lots held per asset).
      break_exit — hard exit when the grid breaks: on range exit, CLOSE
                   all lots at the close (realise) instead of holding
                   them (the DGT hold that builds the big unrealised DD).
      atr_spacing— spacing scaled to volatility: spacing at each anchor
                   = clamp(ATR/close, 0.5%, 2%).
      max_unreal_dd — hard stop on unrealised drawdown: if the equity
                   curve (realised + unrealised) falls $X below its
                   peak, close all lots and HALT the grid for the rest
                   of this split-run.
    Returns (stats, trades, curve). Stats carry staticDD/peakDD from the
    per-asset equity curve (realised + unrealised), plus 'halted'.
    `curve` is the per-bar [(ts, equity+mark)] series so the caller can
    build the TRUE combined account curve across assets (summing the
    three assets' curves bar by bar) — the honest pooled DD, which
    neither the worst-single-asset DD nor the pooled-realised-trade DD
    captures on its own. (v2 reported max(worst-asset equity DD,
    pooled realised-trade DD) — a hybrid; v3 reports the combined
    equity-curve DD as primary and the worst-asset DD alongside.)
    Base case (all fixes off) must reproduce v2's grid_dynamic."""
    fee = fee_bps / 10000.0
    slip = slip_bps / 10000.0
    end = ctx.n if end is None else min(end, ctx.n)
    trades = []
    lots = []
    anchor = None
    anchor_bar = 0
    sp = spacing_pct
    equity, peak, mdd, min_eq = 0.0, 0.0, 0.0, 0.0
    halted = False
    curve = []  # [(ts, realised + unrealised equity)] per bar

    def mark(i):
        return sum((ctx.close[i] - lot["entry"]) * lot["qty"] for lot in lots)

    def close_all(i, why):
        nonlocal equity
        c = ctx.close[i]
        for lot in list(lots):
            exit_px = c * (1 - slip)
            gross = (exit_px - lot["entry"]) * lot["qty"]
            fees = (lot["entry"] * lot["qty"] + exit_px * lot["qty"]) * fee
            pnl = round(gross - fees, 2)
            trades.append(dict(pnl=pnl, side=f"grid-{why}",
                               entry=round(lot["entry"], 2),
                               exit=round(exit_px, 2), bar=i))
            equity += pnl
        lots.clear()

    for i in range(start, end):
        if halted:
            break
        c = ctx.close[i]
        if anchor is None:
            anchor = c
            anchor_bar = i
            if atr_spacing:
                a = ctx.atr[i]
                sp = float(min(0.02, max(0.005, a / c))) if (a == a and c) else 0.01
            continue
        top = anchor * (1 + levels * sp)
        bot = anchor * (1 - levels * sp)
        if c >= top or c <= bot or i - anchor_bar >= reset_bars:
            if (c >= top or c <= bot) and break_exit:
                close_all(i, "break")
            anchor = c
            anchor_bar = i
            if atr_spacing:
                a = ctx.atr[i]
                sp = float(min(0.02, max(0.005, a / c))) if (a == a and c) else 0.01
        for lot in list(lots):
            target = anchor * (1 - (lot["level_k"] - 1) * sp) \
                if lot.get("anchor") == anchor else lot["target"]
            if c >= target:
                exit_px = c * (1 - slip)
                gross = (exit_px - lot["entry"]) * lot["qty"]
                fees = (lot["entry"] * lot["qty"] + exit_px * lot["qty"]) * fee
                trades.append(dict(pnl=round(gross - fees, 2), side="grid-sell",
                                   entry=round(lot["entry"], 2), exit=round(exit_px, 2),
                                   bar=i))
                equity += trades[-1]["pnl"]
                lots.remove(lot)
        cur = equity + mark(i)
        peak = max(peak, cur)
        mdd = max(mdd, peak - cur)
        min_eq = min(min_eq, cur)
        curve.append((int(ctx.ts[i]), round(cur, 2)))
        if max_unreal_dd is not None and peak - cur >= max_unreal_dd:
            close_all(i, "ddstop")
            halted = True
            peak = max(peak, equity)
            mdd = max(mdd, peak - equity)
            min_eq = min(min_eq, equity)
            break
        if np.isnan(ctx.adx[i]) or ctx.adx[i] >= adx_gate:
            continue
        if max_lots is not None and len(lots) >= max_lots:
            continue
        for k in range(1, levels + 1):
            lvl = anchor * (1 - k * sp)
            if c <= lvl and not any(lot["level_k"] == k and lot.get("anchor") == anchor
                                    for lot in lots):
                if max_lots is not None and len(lots) >= max_lots:
                    break
                fill = c * (1 + slip)
                qty = leg_notional / fill
                lots.append(dict(level_k=k, entry=fill, qty=qty, anchor=anchor,
                                 target=anchor * (1 - (k - 1) * sp)))
    if lots:
        close_all(end - 1, "close")
        cur = equity
        peak = max(peak, cur)
        mdd = max(mdd, peak - cur)
        min_eq = min(min_eq, cur)
        curve.append((int(ctx.ts[end - 1]), round(cur, 2)))
    s = stats_split(trades)
    s["staticDD"] = round(-min_eq if min_eq < 0 else 0.0, 2)
    s["peakDD"] = round(mdd, 2)
    s["minEq"] = round(PAPER + min_eq, 2)
    s["maxDD"] = s["peakDD"]
    s["halted"] = halted
    return s, trades, curve


def _combined_curve_dd(curves):
    """Static + peak DD of the combined account curve: sum the assets'
    (realised + unrealised) equity bar by bar on shared timestamps."""
    tot = {}
    for curve in curves:
        for ts, eq in curve:
            tot[ts] = tot.get(ts, 0.0) + eq
    eq, peak, peak_dd, min_eq = 0.0, 0.0, 0.0, 0.0
    for ts in sorted(tot):
        eq = tot[ts]
        peak = max(peak, eq)
        peak_dd = max(peak_dd, peak - eq)
        min_eq = min(min_eq, eq)
    return (round(-min_eq if min_eq < 0 else 0.0, 2), round(peak_dd, 2))


def run_grid_config(ctxs1h, fee_bps, slip_bps, **kw):
    """Run one grid config separately on train and test per asset.
    Pooled exp/PF/net/n come from pooled realised trades; static/peak DD
    is the COMBINED account equity-curve DD (all three assets' realised
    + unrealised equity summed bar by bar — the real $10k account).
    Worst-single-asset DD is reported alongside for comparison with v2,
    whose hybrid was max(worst-asset equity DD, pooled realised-trade DD)."""
    tr_tr, te_tr = [], []
    tr_curves, te_curves = [], []
    tr_sdd = tr_pdd = te_sdd = te_pdd = 0.0
    halted_any = False
    for ctx, sym in zip(ctxs1h, ASSETS):
        s_tr, t_tr, c_tr = grid_dynamic_v3(ctx, fee_bps, slip_bps, start=250, end=ctx.split, **kw)
        s_te, t_te, c_te = grid_dynamic_v3(ctx, fee_bps, slip_bps, start=ctx.split, end=ctx.n, **kw)
        for t in t_tr:
            t["asset"] = sym
            t["ts"] = int(ctx.ts[min(t["bar"], ctx.n - 1)])
        for t in t_te:
            t["asset"] = sym
            t["ts"] = int(ctx.ts[min(t["bar"], ctx.n - 1)])
        tr_tr.extend(t_tr)
        te_tr.extend(t_te)
        tr_curves.append(c_tr)
        te_curves.append(c_te)
        tr_sdd = max(tr_sdd, s_tr["staticDD"])
        tr_pdd = max(tr_pdd, s_tr["peakDD"])
        te_sdd = max(te_sdd, s_te["staticDD"])
        te_pdd = max(te_pdd, s_te["peakDD"])
        halted_any = halted_any or s_tr["halted"] or s_te["halted"]
    tr_comb_sdd, tr_comb_pdd = _combined_curve_dd(tr_curves)
    te_comb_sdd, te_comb_pdd = _combined_curve_dd(te_curves)
    s_train = stats3(tr_tr)
    s_train["staticDD"], s_train["peakDD"] = tr_comb_sdd, tr_comb_pdd
    s_train["worstStaticDD"], s_train["worstPeakDD"] = round(tr_sdd, 2), round(tr_pdd, 2)
    s_train["minEq"] = round(PAPER - tr_comb_sdd, 2)
    s_test = stats3(te_tr)
    s_test["staticDD"], s_test["peakDD"] = te_comb_sdd, te_comb_pdd
    s_test["worstStaticDD"], s_test["worstPeakDD"] = round(te_sdd, 2), round(te_pdd, 2)
    s_test["minEq"] = round(PAPER - te_comb_sdd, 2)
    s_all = stats3(tr_tr + te_tr)
    s_all["staticDD"] = round(max(tr_comb_sdd, te_comb_sdd), 2)
    s_all["peakDD"] = round(max(tr_comb_pdd, te_comb_pdd), 2)
    s_all["worstStaticDD"] = round(max(tr_sdd, te_sdd), 2)
    s_all["worstPeakDD"] = round(max(tr_pdd, te_pdd), 2)
    s_all["minEq"] = round(PAPER - s_all["staticDD"], 2)
    s_all["halted"] = halted_any
    s_test["halted"] = halted_any
    return s_train, s_test, s_all, tr_tr + te_tr


def section_grid(results, ctxs1h):
    print("\n== §4 DYNAMIC GRID DRAWDOWN FIXES (1h, leg $200, base = v2) ==")
    configs = [
        ("GRID_BASE_v3", {}),  # must reproduce v2: Kraken test net +$1,161, pDD $1,007
        ("GRID_ADX15", dict(adx_gate=15.0)),
        ("GRID_ADX20", dict(adx_gate=20.0)),
        ("GRID_MAXLOT3", dict(max_lots=3)),
        ("GRID_MAXLOT5", dict(max_lots=5)),
        ("GRID_BREAKEXIT", dict(break_exit=True)),
        ("GRID_ATRSPACING", dict(atr_spacing=True)),
        ("GRID_DDSTOP100", dict(max_unreal_dd=100.0)),
        ("GRID_DDSTOP150", dict(max_unreal_dd=150.0)),
        ("GRID_COMBINED", dict(adx_gate=20.0, max_lots=5, break_exit=True,
                               atr_spacing=True, max_unreal_dd=150.0)),
        ("GRID_COMBINED_NOBREAK", dict(adx_gate=20.0, max_lots=5,
                                       atr_spacing=True, max_unreal_dd=150.0)),
    ]
    for name, kw in configs:
        for mode, (fb, sb) in (("hard", (10.0, 5.0)), ("kraken", (2.0, 1.0))):
            s_train, s_test, s_all, trades = run_grid_config(ctxs1h, fb, sb, **kw)
            key = f"{name}__{mode}"
            results[key] = dict(train=s_train, test=s_test, all=s_all)
            ok = gate_pass(s_test, s_all) and s_test["pf"] > 1.5
            print(f"{name:<22} {mode:<6} TRAIN n={s_train['n']:>5} exp=${s_train['exp']:>+6} "
                  f"PF={s_train['pf']:>5} net=${s_train['net']:>+9} sDD=${s_train['staticDD']:>7} pDD=${s_train['peakDD']:>7} | "
                  f"TEST n={s_test['n']:>5} exp=${s_test['exp']:>+6} PF={s_test['pf']:>5} "
                  f"net=${s_test['net']:>+9} sDD=${s_test['staticDD']:>7} pDD=${s_test['peakDD']:>7} "
                  f"halted={s_test['halted']} [{'PASS-v3grid' if ok else 'fail'}]")
    save(results)


# ============================================================ §5 mean reversion v2
def make_mr_v3(z_thresh, sl_pct, exit_mode="mean", adx_gate=25.0):
    """Mean reversion v2: wide stops. SL = max(recent low, entry*(1-sl_pct)).
    TP = 20-period mean ('mean') or 5-period MA ('sma5'). RSI(14)<30,
    ADX<25 (ranging only), BTC/ETH only, long-only."""
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
        if z >= z_thresh:
            return None
        c = ctx.close[i]
        tp = ctx.sma20[i] if exit_mode == "mean" else ctx.sma5[i]
        if np.isnan(tp) or tp <= c * 1.001:
            return None
        sl = max(ctx.low[max(0, i - 4):i + 1].min() * 0.999, c * (1 - sl_pct))
        if sl >= c:
            return None
        return ("long", tp, sl, {})
    return fn


def section_mr(results, ctxs):
    print("\n== §5 MEAN REVERSION v2 (wide stops / time exits, exit at mean) ==")
    # 1h: z(3) x SL(1.5/3/5%) x hold(24h/48h) = 18 variants
    # 15m: z(3) x SL(1.5/3/5%) x hold(96 bars=24h) = 9 variants
    variants = []
    for z in (-1.5, -2.0, -2.5):
        for sl in (0.015, 0.03, 0.05):
            variants.append((f"MRv2_z{abs(z):.1f}_SL{int(sl*100)}_H24_1h", "1h", z, sl, 24))
            variants.append((f"MRv2_z{abs(z):.1f}_SL{int(sl*100)}_H48_1h", "1h", z, sl, 48))
    for z in (-1.5, -2.0, -2.5):
        for sl in (0.015, 0.03, 0.05):
            variants.append((f"MRv2_z{abs(z):.1f}_SL{int(sl*100)}_H96_15m", "15m", z, sl, 96))
    for tag, tf, z, sl, hold in variants:
        fn = make_mr_v3(z, sl)
        for mode, (fb, sb) in (("hard", (10.0, 5.0)), ("kraken", (2.0, 1.0))):
            r = run_strategy(ctxs[tf], fn, fb, sb, risk_pct=0.0025,
                             max_hold=hold, asset_filter=["BTCUSDT", "ETHUSDT"])
            for t in r["trades"]:
                t["ts"] = int(dict(zip(ASSETS, [c.ts for c in ctxs[tf]]))[t["asset"]][t["bar"]])
            tr, te, al = split_stats3(r["trades"], ctxs[tf])
            key = f"{tag}__{mode}"
            results[key] = dict(train=tr, test=te, all=al)
            ok = gate_pass(te, al)
            print(f"{tag:<28} {mode:<6} TRAIN n={tr['n']:>4} exp=${tr['exp']:>+6} PF={tr['pf']:>5} "
                  f"net=${tr['net']:>+8} sDD=${tr['staticDD']:>6} | TEST n={te['n']:>4} "
                  f"exp=${te['exp']:>+6} PF={te['pf']:>5} net=${te['net']:>+8} "
                  f"sDD=${te['staticDD']:>6} pDD=${te['peakDD']:>6} [{'PASS' if ok else 'fail'}]")
    save(results)


# ============================================================ §6 4h / daily
def _run_single_tf(results, ctxs_by_tf, name, fn, tf, risk=0.005, mh=100):
    for mode, (fb, sb) in (("hard", (10.0, 5.0)), ("kraken", (2.0, 1.0))):
        r = run_strategy(ctxs_by_tf[tf], fn, fb, sb, risk_pct=risk, max_hold=mh)
        for t in r["trades"]:
            t["ts"] = int(dict(zip(ASSETS, [c.ts for c in ctxs_by_tf[tf]]))[t["asset"]][t["bar"]])
        tr, te, al = split_stats3(r["trades"], ctxs_by_tf[tf])
        key = f"{name}_{tf}__{mode}"
        results[key] = dict(train=tr, test=te, all=al, dropped_short=r["dropped_short"])
        ok = gate_pass(te, al)
        print(f"{name}_{tf:<3} {mode:<6} TRAIN n={tr['n']:>4} exp=${tr['exp']:>+6} PF={tr['pf']:>5} "
              f"net=${tr['net']:>+8} sDD=${tr['staticDD']:>6} | TEST n={te['n']:>4} "
              f"exp=${te['exp']:>+6} PF={te['pf']:>5} net=${te['net']:>+8} "
              f"sDD=${te['staticDD']:>6} pDD=${te['peakDD']:>6} [{'PASS' if ok else 'fail'}]")


def sig_turtle_short_diag(ctx, i):
    """DIAGNOSTIC ONLY — short Turtle: breakdown below prior-20 low.
    Shorts are NOT Kraken-eligible (1x spot, no leverage). This run is
    labelled DIAG-SHORT, never gated, never stacked, never funded."""
    if i < 250 or np.isnan(ctx.atr[i]):
        return None
    c = ctx.close[i]
    lo20 = ctx.low[i - 20:i].min()
    if c >= lo20:
        return None
    a = ctx.atr[i]
    return ("short", c - 2.0 * a, c + 2.0 * a, {"exit_below_lo": 10})


def simulate_short(ctx, sig_fn, fee_bps, slip_bps, risk_pct=0.005,
                   max_hold=100, start=250, end=None):
    """Minimal short-only engine for the DIAG-SHORT run: fill next bar
    open, SL first, TP second, TIME exit. Mirrors simulate_v2 semantics."""
    fee = fee_bps / 10000.0
    slip = slip_bps / 10000.0
    n = ctx.n if end is None else min(end, ctx.n)
    trades = []
    pos = None
    pending = None
    for i in range(start, n - 1):
        o, h, l, cl = ctx.open[i], ctx.high[i], ctx.low[i], ctx.close[i]
        if pending is not None:
            tp, sl = pending
            fill = o * (1 - slip)
            d = abs(sl - fill)
            qty = (risk_pct * PAPER) / max(d, fill * 0.001)
            if qty * fill > 2000.0:
                qty = 2000.0 / fill
            pos = dict(entry=fill, tp=tp, sl=sl, qty=qty, opened=i, bar=i)
            pending = None
        if pos is not None:
            exit_px, why = None, None
            if h >= pos["sl"]:
                exit_px, why = pos["sl"] * (1 + slip), "SL"
            elif l <= pos["tp"]:
                exit_px, why = pos["tp"] * (1 + slip), "TP"
            if exit_px is None and i - pos["opened"] >= max_hold:
                exit_px, why = cl * (1 + slip), "TIME"
            if exit_px is not None:
                gross = (pos["entry"] - exit_px) * pos["qty"]
                fees = (pos["entry"] * pos["qty"] + exit_px * pos["qty"]) * fee
                trades.append(dict(pnl=round(gross - fees, 2), side="short", why=why,
                                   entry=round(pos["entry"], 4), exit=round(exit_px, 4),
                                   bar=pos["bar"]))
                pos = None
        if pos is None and pending is None:
            sig = sig_fn(ctx, i)
            if sig is not None and sig[0] == "short":
                pending = (sig[1], sig[2])
    return trades


def section_tf(results, ctxs):
    print("\n== §6 4h / DAILY versions of best v2 strategies (long-only) ==")
    ctxs_daily = [load_daily(s) for s in ASSETS]
    print(f"daily data: {ctxs_daily[0].n} bars/asset, split@{ctxs_daily[0].split}, "
          f"test bars={ctxs_daily[0].n - ctxs_daily[0].split}")
    ctxs_by_tf = {"4h": ctxs["4h"], "1d": ctxs_daily}
    # Trend Following + Pullback + Turtle were 4h in v2; here they get
    # daily. TrendRider was 1h in v2; here it gets 4h AND daily.
    for name, fn, risk in (("TREND_FOLLOW", sig_trend_follow, 0.005),
                           ("PULLBACK", sig_pullback, 0.005),
                           ("TURTLE", sig_turtle, 0.002)):
        _run_single_tf(results, ctxs_by_tf, name, fn, "1d", risk=risk)
    for name, fn, risk in (("TRENDRIDER", sig_trendrider, 0.005),):
        _run_single_tf(results, ctxs_by_tf, name, fn, "4h", risk=risk)
        _run_single_tf(results, ctxs_by_tf, name, fn, "1d", risk=risk)
    # NOTE: Trend Following / Pullback / Turtle on 4h are the v2 runs
    # themselves (re-reported under static DD in §7); not re-run here.
    # --- DIAG-SHORT: Turtle short on 4h, both modes, labelled, ungated.
    print("-- DIAG-SHORT (shorts NOT Kraken-eligible; diagnostic only) --")
    for mode, (fb, sb) in (("hard", (10.0, 5.0)), ("kraken", (2.0, 1.0))):
        all_tr = []
        for ctx, sym in zip(ctxs["4h"], ASSETS):
            tr = simulate_short(ctx, sig_turtle_short_diag, fb, sb, risk_pct=0.002)
            for t in tr:
                t["asset"] = sym
                t["ts"] = int(ctx.ts[t["bar"]])
            all_tr.extend(tr)
        tr_s, te_s, al_s = split_stats3(all_tr, ctxs["4h"])
        results[f"TURTLE_SHORT_DIAG_4H__{mode}"] = dict(train=tr_s, test=te_s, all=al_s)
        print(f"TURTLE_SHORT_DIAG_4H {mode:<6} TEST n={te_s['n']:>4} exp=${te_s['exp']:>+6} "
              f"PF={te_s['pf']:>5} net=${te_s['net']:>+8} sDD=${te_s['staticDD']:>6} "
              f"pDD=${te_s['peakDD']:>6} [DIAG ONLY — never funded]")
    save(results)


# ============================================================ §7 full v2 re-run, static DD
SINGLE_V2 = [
    ("TREND_FOLLOW_4H", "4h", sig_trend_follow, 0.005, 100, None),
    ("PULLBACK_4H", "4h", sig_pullback, 0.005, 100, None),
    ("RSI2_RANGE_1H", "1h", sig_rsi2, 0.0025, 100, ["BTCUSDT", "ETHUSDT"]),
    ("VWAP_BOUNCE_15M", "15m", sig_vwap_bounce, 0.0025, 100, None),
    ("VWAP_RETEST_15M", "15m", sig_vwap_retest, 0.0025, 100, None),
    ("TRENDRIDER_1H", "1h", sig_trendrider, 0.005, 100, None),
    ("TURTLE_4H", "4h", sig_turtle, 0.002, 100, None),
    ("TURTLE_TP1_4H", "4h", sig_turtle_tp1, 0.002, 100, None),
    ("EMA_RIBBON_15M", "15m", sig_ema_ribbon, 0.0025, 100, None),
    ("RANGE_1H", "1h", sig_range, 0.005, 100, None),
    ("VOL_BREAKOUT_1H", "1h", sig_vol_breakout, 0.005, 100, None),
    ("TREND_ASSASSIN_1H", "1h", sig_trend_assassin_v2, 0.005, 100, None),
    ("MEAN_REV_ZSCORE_1H", "1h", sig_mean_rev_zscore, 0.0025, 100,
     ["BTCUSDT", "ETHUSDT"]),
]


def section_static(results, ctxs):
    print("\n== §7 FULL v2 14-STRATEGY SET UNDER STATIC DRAWDOWN ==")
    modes = {"hard": (10.0, 5.0), "kraken": (2.0, 1.0)}
    passing = {}
    for mode, (fb, sb) in modes.items():
        passing[mode] = []
        for name, tf, fn, risk, mh, filt in SINGLE_V2:
            r = run_strategy(ctxs[tf], fn, fb, sb, risk_pct=risk, max_hold=mh,
                             asset_filter=filt)
            ts_by = {sym: ctx.ts for ctx, sym in zip(ctxs[tf], ASSETS)}
            for t in r["trades"]:
                t["ts"] = int(ts_by[t["asset"]][t["bar"]])
            tr, te, al = split_stats3(r["trades"], ctxs[tf])
            results[f"{name}__{mode}"] = dict(train=tr, test=te, all=al,
                                              dropped_short=r["dropped_short"])
            _fmt3(name, mode, tr, te)
            if gate_pass(te, al):
                passing[mode].append((name, r["trades"]))
        # Dynamic Grid base (v2 config), static + peak DD, worst asset.
        s_train, s_test, s_all, g_trades = run_grid_config(ctxs["1h"], fb, sb)
        results[f"DYN_GRID_1H__{mode}"] = dict(train=s_train, test=s_test, all=s_all)
        _fmt3("DYN_GRID_1H", mode, s_train, s_test)
        if gate_pass(s_test, s_all):
            passing[mode].append(("DYN_GRID_1H", g_trades))
        # Kalman pairs (1h BTC/ETH)
        p_trades = pairs_kalman(ctxs["1h"][0], ctxs["1h"][1], fb, sb)
        ts_map = {"BTCUSDT": ctxs["1h"][0].ts, "ETHUSDT": ctxs["1h"][1].ts}
        for t in p_trades:
            t["ts"] = int(ts_map[t["asset"]][t["bar"]])
        p_train, p_test, p_all = split_stats3(p_trades, ctxs["1h"])
        results[f"KALMAN_PAIRS_1H__{mode}"] = dict(train=p_train, test=p_test, all=p_all)
        _fmt3("KALMAN_PAIRS_1H", mode, p_train, p_test)
        if gate_pass(p_test, p_all):
            passing[mode].append(("KALMAN_PAIRS_1H", p_trades))
        # Momentum rotation (1h, weekly)
        m_trades = momentum_rotation(ctxs["1h"], fb, sb)
        m_train, m_test, m_all = split_stats3(m_trades, ctxs["1h"])
        results[f"MOMENTUM_ROT_1H__{mode}"] = dict(train=m_train, test=m_test, all=m_all)
        _fmt3("MOMENTUM_ROT_1H", mode, m_train, m_test)
        if gate_pass(m_test, m_all):
            passing[mode].append(("MOMENTUM_ROT_1H", m_trades))
        # --- stacked swarm: only v3-gate passers, chronological equity ---
        stack = []
        for nm, tr in passing[mode]:
            stack.extend(tr)
        stack_sorted = sorted(stack, key=lambda t: t.get("ts", 0))
        s_stack = stats3(stack_sorted)
        results[f"STACK_PASSING__{mode}"] = dict(
            members=[nm for nm, _ in passing[mode]], all=s_stack)
        print(f"STACK ({mode}): members={[nm for nm, _ in passing[mode]]} "
              f"n={s_stack['n']} net=${s_stack['net']} staticDD=${s_stack['staticDD']} "
              f"peakDD=${s_stack['peakDD']} minEq=${s_stack['minEq']} "
              f"Kraken target +$1,200 / static DD <=$300")
    save(results)


# ------------------------------------------------------------------ main
SECTIONS = {
    "random": section_random,
    "dump": section_dump,
    "grid": section_grid,
    "mr": section_mr,
    "tf": section_tf,
    "static": section_static,
}


def main():
    args = sys.argv[1:] or ["all"]
    wanted = list(SECTIONS) if "all" in args else [a for a in args if a in SECTIONS]
    if not wanted:
        print("usage: experiments_v3.py [random|dump|grid|mr|tf|static|all]")
        sys.exit(2)
    results = {}
    if os.path.exists(RESULTS_PATH):
        try:
            results = json.load(open(RESULTS_PATH))
        except Exception:
            results = {}
    ctxs = {}
    need = set()
    if "random" in wanted:
        need.update(("1h", "4h"))
    if "dump" in wanted:
        need.add("15m")
    if "grid" in wanted:
        need.add("1h")
    if "mr" in wanted:
        need.update(("1h", "15m"))
    if "tf" in wanted:
        need.add("4h")
    if "static" in wanted:
        need.update(("1h", "4h", "15m"))
    for tf in sorted(need):
        ctxs[tf] = [load_v2(s, tf) for s in ASSETS]
        print(f"{tf} data: {ctxs[tf][0].n} bars/asset, split@{ctxs[tf][0].split} "
              f"(2026-01-01), test bars={ctxs[tf][0].n - ctxs[tf][0].split}")
    if "random" in wanted:
        section_random(results, ctxs)
    if "dump" in wanted:
        section_dump(results, ctxs["15m"])
    if "grid" in wanted:
        section_grid(results, ctxs["1h"])
    if "mr" in wanted:
        section_mr(results, ctxs)
    if "tf" in wanted:
        section_tf(results, ctxs)
    if "static" in wanted:
        section_static(results, ctxs)
    save(results)
    print("\nSaved experiments_v3_results.json")


if __name__ == "__main__":
    main()

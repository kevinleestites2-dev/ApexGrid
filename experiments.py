"""experiments.py — FAST harness for new / ported strategies.

Why this file exists: backtest.py recomputes indicators on the full window
every bar (O(n^2)), so a 1h run takes ~8 minutes. This harness precomputes
every indicator ONCE (vectorized pandas) and then runs a tight O(n) loop,
so a new idea can be tested in seconds — with the SAME fill/exit engine
semantics as backtest.py (next-bar-open fill, TP/SL on bar high/low,
10bps fee per side, 5bps slippage, time-stop).

RULE: a strategy only counts as "proven" if it backtests POSITIVE on
expectancy on real Binance.US history, with fees + slippage, and survives
the Kraken 3% drawdown test. Theory alone earns nothing.

Strategies tested here:
  PORT  DUMP_HEDGE_15  — Kevin's favourite, OpenTrade zeus_prime_v2.py L603.
                         15-min markets, >=3% dump detected in the window,
                         buy the dumped side at 30% size, TP +5% / SL -10%.
                         The YES+NO<=0.98 both-sides hedge leg is prediction-
                         market-only and is NOT portable to spot — see README.
  NEW   DOUBLE_PANIC    — dump >=3% in 15m AND FOMO/PANIC extreme fear
                         (RSI<25) must agree. Two independent panic signals.
  NEW   ECHO_TREND      — Echo FFT cycle + shape match, gated to TREND
                         regime, with Trend-Assassin-style crowd exit
                         (volume climax >2x average exits early).
  NEW   ASCETIX_SPOT    — Ascetix 4-signal confluence adapted to spot 1x,
                         no leverage: momentum + RSI zone + volume spike +
                         bar pressure; 3/4 must agree; 25% size.
  NEW   META_LEARNER    — Q-learning that learns WHICH strategy to trust in
                         WHICH regime (state=regime, action=strategy).
                         Reward = expectancy-normalised pnl/risk.

Usage:  python3 experiments.py            (runs everything, prints scoreboard)
        python3 experiments.py dump       (only the 15m dump family)
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import FEE_BPS_PER_SIDE as FEE_BPS, SLIPPAGE_BPS, MAX_HOLD_BARS
from config import NOTIONAL_PER_TRADE as NOTIONAL
from indicators import atr, avg_volume, bollinger, regime, rsi_wilder, sma

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FEE = FEE_BPS / 10000.0
SLIP = SLIPPAGE_BPS / 10000.0
ASSETS_1H = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
ASSETS_15M = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


# ------------------------------------------------------------------ data
def load(symbol, tf):
    path = os.path.join(DATA, f"{symbol}_{tf}.json")
    raw = json.load(open(path))
    if raw and isinstance(raw[0], list):
        # raw Binance klines: [t, open, high, low, close, volume, ...]
        df = pd.DataFrame(raw, columns=["t", "open", "high", "low", "close",
                                        "volume", "_ct", "_q", "_n", "_tb",
                                        "_tq", "_x"][:len(raw[0])])
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
    else:
        df = pd.DataFrame(raw)
    df["rsi"] = rsi_wilder(df["close"])
    df["atr"] = atr(df)
    df["sma20"] = sma(df["close"], 20)
    df["sma50"] = sma(df["close"], 50)
    df["bb_up"], df["bb_mid"], df["bb_dn"] = bollinger(df["close"])
    df["vol_avg"] = avg_volume(df["volume"])
    return df


class Ctx:
    """Numpy views of one asset's precomputed frame (fast per-bar access)."""

    def __init__(self, df):
        self.df = df
        for col in ["open", "high", "low", "close", "volume",
                    "rsi", "atr", "sma20", "sma50", "bb_up", "bb_mid",
                    "bb_dn", "vol_avg"]:
            setattr(self, col, df[col].to_numpy(dtype=float))
        self.n = len(df)
        self._echo_cache = {}

    def regime_at(self, i):
        return regime(self.df, i)

    def echo_agrees(self, i):
        """Echo FFT + shape match, cached every 16 bars (same thresholds
        as strategies.py EchoAgent). Returns True/False.

        BUG FIX (v1, 2026-11-10): the cache was keyed by i//16 but the
        computation used the CURRENT bar i — so the cached value depended
        on which bar of the block first called it, and two runs sharing
        a Ctx gave different results (GRID_ECHO_NOSTOP: n=784 fresh vs
        n=776 after other variants ran on the same ctx). The value is
        now computed at the block's first bar i0 = (i//16)*16 and cached
        under i0, so it is identical regardless of call order.
        """
        i0 = (i // 16) * 16
        if i0 in self._echo_cache:
            return self._echo_cache[i0]
        ok = False
        closes = self.close
        if i0 >= 256:
            seg = closes[i0 - 256:i0]
            seg = seg - seg.mean()
            spec = np.abs(np.fft.rfft(seg))
            freqs = np.fft.rfftfreq(len(seg))
            with np.errstate(divide="ignore", invalid="ignore"):
                periods = np.where(freqs > 0, 1.0 / np.where(freqs == 0, np.nan, freqs), np.nan)
            dom = None
            if len(spec) > 1:
                order = np.argsort(spec[1:])[::-1] + 1
                for idx in order:
                    if 8 <= periods[idx] <= 32:
                        dom = periods[idx]
                        break
            if dom is not None:
                cur = closes[i0 - 16:i0]
                cur_n = (cur - cur.mean()) / (cur.std() or 1.0)
                best_corr, best_end = -1.0, None
                for start in range(max(0, i0 - 1000), i0 - 32, 8):
                    w = closes[start:start + 16]
                    if len(w) < 16:
                        continue
                    w_n = (w - w.mean()) / (w.std() or 1.0)
                    c = float(np.corrcoef(cur_n, w_n)[0, 1])
                    if c > best_corr:
                        best_corr, best_end = c, start + 16
                if best_corr > 0.85 and best_end is not None and best_end + 8 < i0:
                    follow = (closes[best_end + 8] - closes[best_end]) / closes[best_end]
                    ok = follow > 0.01
        self._echo_cache[i0] = ok
        return ok


# ------------------------------------------------------------------ engine
def _stats(trades):
    """Same metrics as backtest.py / ledger.py."""
    if not trades:
        return dict(n=0, win=0.0, avgW=0.0, avgL=0.0, exp=0.0, pf=0.0,
                    net=0.0, maxDD=0.0)
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(pnls)
    avg_w = sum(wins) / len(wins) if wins else 0.0
    avg_l = abs(sum(losses) / len(losses)) if losses else 0.0
    exp = win_rate * avg_w - (1 - win_rate) * avg_l
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float("inf")
    eq, peak, mdd = 0.0, 0.0, 0.0
    for p in pnls:
        eq += p
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    return dict(n=len(pnls), win=round(win_rate * 100, 1), avgW=round(avg_w, 2),
                avgL=round(avg_l, 2), exp=round(exp, 2),
                pf=round(pf, 2) if pf != float("inf") else 999.0,
                net=round(sum(pnls), 2), maxDD=round(mdd, 2))


def simulate(ctx, signal_fn, size_pct=1.0, max_hold=MAX_HOLD_BARS,
             train_end=None, collect_test=False, cooldown_bars=0):
    """Run one strategy over one asset.

    signal_fn(ctx, i) -> (side, tp, sl) | None, side in {'long','short'}.
    tp/sl are absolute price levels set at signal time.
    cooldown_bars: minimum bars between entries (Ascetix 15-bar rule).
    Returns (all_trades, test_trades) — test_trades only when collect_test
    and train_end is set (bars >= train_end, Q frozen by the caller).
    """
    trades, test_trades = [], []
    pos = None          # dict(side, entry, tp, sl, qty, notional, opened_bar, risk)
    pending = None      # signal waiting for next-bar-open fill
    last_entry_bar = -10 ** 9
    for i in range(100, ctx.n - 1):
        o, h, l, c = ctx.open[i], ctx.high[i], ctx.low[i], ctx.close[i]
        # --- fill pending entry at this bar's open
        if pending is not None:
            side, tp, sl = pending
            fill = o * (1 + SLIP) if side == "long" else o * (1 - SLIP)
            notional = NOTIONAL * size_pct
            qty = notional / fill
            risk = abs(fill - sl) * qty if sl else notional * 0.10
            pos = dict(side=side, entry=fill, tp=tp, sl=sl, qty=qty,
                       notional=notional, opened=i, risk=max(risk, 1.0),
                       test=(train_end is not None and i >= train_end))
            pending = None
            last_entry_bar = i
        # --- manage open position: TP / SL / time-stop on this bar
        if pos is not None:
            exit_px, why = None, None
            if pos["side"] == "long":
                if l <= pos["sl"]:
                    exit_px, why = pos["sl"] * (1 - SLIP), "SL"
                elif h >= pos["tp"]:
                    exit_px, why = pos["tp"] * (1 - SLIP), "TP"
            else:
                if h >= pos["sl"]:
                    exit_px, why = pos["sl"] * (1 + SLIP), "SL"
                elif l <= pos["tp"]:
                    exit_px, why = pos["tp"] * (1 + SLIP), "TP"
            if exit_px is None and i - pos["opened"] >= max_hold:
                exit_px, why = c * (1 - SLIP) if pos["side"] == "long" else c * (1 + SLIP), "TIME"
            if exit_px is not None:
                gross = (exit_px - pos["entry"]) * pos["qty"] if pos["side"] == "long" \
                    else (pos["entry"] - exit_px) * pos["qty"]
                fees = (pos["entry"] * pos["qty"] + exit_px * pos["qty"]) * FEE
                t = dict(pnl=round(gross - fees, 2), side=pos["side"], why=why,
                         entry=round(pos["entry"], 4), exit=round(exit_px, 4),
                         risk=round(pos["risk"], 2))
                trades.append(t)
                if pos["test"]:
                    test_trades.append(t)
                pos = None
        # --- new signal (only when flat, and outside the cooldown)
        if pos is None and pending is None and i - last_entry_bar >= cooldown_bars:
            sig = signal_fn(ctx, i)
            if sig is not None:
                pending = sig
    return trades, test_trades


# ------------------------------------------------------------------ signals
def sig_dump_15(ctx, i):
    """PORT DumpAndHedgeStrategy (zeus L603): 15-min window, >=3% intrabar
    dump -> buy the dumped side at 30% size. TP +5% / SL -10%."""
    o, l, c = ctx.open[i], ctx.low[i], ctx.close[i]
    if o > 0 and (o - l) / o >= 0.03:
        return ("long", c * 1.05, c * 0.90)
    return None


def sig_double_panic(ctx, i):
    """NEW: dump >=3% in 15m AND RSI<25 (FOMO/PANIC extreme fear agrees)."""
    if sig_dump_15(ctx, i) is None:
        return None
    if not np.isnan(ctx.rsi[i]) and ctx.rsi[i] < 25:
        c = ctx.close[i]
        return ("long", c * 1.05, c * 0.90)
    return None


def sig_echo_trend(ctx, i):
    """NEW: Echo FFT+shape agrees + TREND_UP regime + close above SMA20.
    Crowd exit: volume climax handled by the engine via max_hold/TP/SL;
    a >2x volume bar while in profit exits at close (checked in runner)."""
    if ctx.regime_at(i) != "TREND_UP":
        return None
    if np.isnan(ctx.sma20[i]) or ctx.close[i] <= ctx.sma20[i]:
        return None
    if not ctx.echo_agrees(i):
        return None
    c, a = ctx.close[i], ctx.atr[i]
    if np.isnan(a):
        return None
    return ("long", c + 2.0 * a, c - 1.5 * a)


def sig_ascetix_spot(ctx, i):
    """NEW: Ascetix 4-signal confluence, spot 1x long-only. 3/4 must vote UP:
    momentum (5-bar return > +0.5%), RSI in healthy zone (40-65),
    volume spike (>1.5x avg with a green close), bar pressure
    (close in upper third of the bar range). 25% size, 15-bar cooldown
    is enforced by the caller via last-entry tracking."""
    votes = 0
    if i >= 5 and ctx.close[i] > ctx.close[i - 5] * 1.005:
        votes += 1
    if not np.isnan(ctx.rsi[i]) and 40 < ctx.rsi[i] < 65:
        votes += 1
    if (not np.isnan(ctx.vol_avg[i]) and ctx.volume[i] > 1.5 * ctx.vol_avg[i]
            and ctx.close[i] > ctx.open[i]):
        votes += 1
    rng = ctx.high[i] - ctx.low[i]
    if rng > 0 and ctx.close[i] > ctx.low[i] + (2.0 / 3.0) * rng:
        votes += 1
    if votes >= 3:
        c, a = ctx.close[i], ctx.atr[i]
        if np.isnan(a):
            return None
        return ("long", c + 2.0 * a, c - 1.5 * a)
    return None


# --- classic signals (for the meta-learner; mirrors strategies.py) ---
def sig_rsi(ctx, i):
    r = ctx.rsi[i]
    if np.isnan(r):
        return None
    c, a = ctx.close[i], ctx.atr[i]
    if np.isnan(a):
        return None
    if ctx.regime_at(i) != "SIDEWAYS":
        return None
    if r < 30:
        return ("long", c + 2.5 * a, c - 1.5 * a)
    if r > 70:
        return ("short", c - 2.5 * a, c + 1.5 * a)
    return None


def sig_bollinger(ctx, i):
    c = ctx.close[i]
    if np.isnan(ctx.bb_dn[i]) or ctx.regime_at(i) != "SIDEWAYS":
        return None
    a = ctx.atr[i]
    if np.isnan(a):
        return None
    if c <= ctx.bb_dn[i]:
        return ("long", c + 2.5 * a, c - 1.5 * a)
    if c >= ctx.bb_up[i]:
        return ("short", c - 2.5 * a, c + 1.5 * a)
    return None


def sig_breakout(ctx, i):
    if ctx.regime_at(i) not in ("TREND_UP", "TREND_DOWN"):
        return None
    if i < 20 or np.isnan(ctx.vol_avg[i]):
        return None
    c, a = ctx.close[i], ctx.atr[i]
    if np.isnan(a):
        return None
    hi20 = ctx.high[i - 20:i].max()
    lo20 = ctx.low[i - 20:i].min()
    if c > hi20 and ctx.volume[i] > 1.5 * ctx.vol_avg[i]:
        return ("long", c + 2.5 * a, c - 1.5 * a)
    if c < lo20 and ctx.volume[i] > 1.5 * ctx.vol_avg[i]:
        return ("short", c - 2.5 * a, c + 1.5 * a)
    return None


META_STRATEGIES = {
    "RSI_MEAN_REVERSION": sig_rsi,
    "BOLLINGER_FADE": sig_bollinger,
    "BREAKOUT": sig_breakout,
    "ECHO_TREND": sig_echo_trend,
    "ASCETIX_SPOT": sig_ascetix_spot,
}


def run_meta_learner(ctxs, epsilon_train=0.10):
    """NEW META_LEARNER: Q[regime][strategy], epsilon-greedy.
    Trains on the first 70% of bars, frozen on the last 30% (test split).
    One position per asset at a time; reward = clip(pnl/risk, -1, 1)."""
    regimes = ["TREND_UP", "TREND_DOWN", "SIDEWAYS", "UNKNOWN"]
    names = list(META_STRATEGIES)
    Q = {r: {n: 0.0 for n in names} for r in regimes}
    alpha, gamma = 0.10, 0.95
    all_trades, test_trades = [], []
    rng = np.random.default_rng(7)
    for ctx in ctxs:
        n = ctx.n
        train_end = int(n * 0.70)
        pos = None
        pending = None  # (strategy_name, signal, regime_at_signal)
        last_entry_bar = -10 ** 9
        for i in range(100, n - 1):
            o, h, l, c = ctx.open[i], ctx.high[i], ctx.low[i], ctx.close[i]
            frozen = i >= train_end
            eps = 0.02 if frozen else epsilon_train
            if pending is not None:
                sname, (side, tp, sl), reg = pending
                fill = o * (1 + SLIP) if side == "long" else o * (1 - SLIP)
                notional = NOTIONAL
                qty = notional / fill
                risk = max(abs(fill - sl) * qty, 1.0)
                pos = dict(side=side, entry=fill, tp=tp, sl=sl, qty=qty,
                           opened=i, risk=risk, strat=sname, reg=reg,
                           test=frozen)
                pending = None
                last_entry_bar = i
            if pos is not None:
                exit_px, why = None, None
                if pos["side"] == "long":
                    if l <= pos["sl"]:
                        exit_px, why = pos["sl"] * (1 - SLIP), "SL"
                    elif h >= pos["tp"]:
                        exit_px, why = pos["tp"] * (1 - SLIP), "TP"
                else:
                    if h >= pos["sl"]:
                        exit_px, why = pos["sl"] * (1 + SLIP), "SL"
                    elif l <= pos["tp"]:
                        exit_px, why = pos["tp"] * (1 + SLIP), "TP"
                if exit_px is None and i - pos["opened"] >= MAX_HOLD_BARS:
                    exit_px, why = c * (1 - SLIP) if pos["side"] == "long" else c * (1 + SLIP), "TIME"
                if exit_px is not None:
                    gross = (exit_px - pos["entry"]) * pos["qty"] if pos["side"] == "long" \
                        else (pos["entry"] - exit_px) * pos["qty"]
                    fees = (pos["entry"] * pos["qty"] + exit_px * pos["qty"]) * FEE
                    pnl = round(gross - fees, 2)
                    t = dict(pnl=pnl, side=pos["side"], why=why, strat=pos["strat"],
                             reg=pos["reg"])
                    all_trades.append(t)
                    if pos["test"]:
                        test_trades.append(t)
                    if not frozen:
                        reward = max(-1.0, min(1.0, pnl / pos["risk"]))
                        q = Q[pos["reg"]][pos["strat"]]
                        best_next = max(Q[pos["reg"]].values())
                        Q[pos["reg"]][pos["strat"]] = q + alpha * (reward + gamma * best_next - q)
                    pos = None
            if pos is None and pending is None:
                reg = ctx.regime_at(i)
                if rng.random() < eps:
                    sname = names[int(rng.integers(len(names)))]
                else:
                    sname = max(Q[reg], key=lambda k: Q[reg][k])
                sig = META_STRATEGIES[sname](ctx, i)
                if sig is not None:
                    if sname == "ASCETIX_SPOT" and i - last_entry_bar < 15:
                        continue
                    pending = (sname, sig, reg)
    return all_trades, test_trades, Q


# ------------------------------------------------------------------ main
def _fmt(name, s):
    flag = "PROVEN" if (s["exp"] > 0 and s["n"] >= 30) else \
        ("POSITIVE-UNPROVEN" if s["exp"] > 0 else "NEGATIVE")
    print(f"{name:<18} n={s['n']:>4} win={s['win']:>5}% avgW=${s['avgW']:>7} "
          f"avgL=${s['avgL']:>7} exp=${s['exp']:>+7}/trade PF={s['pf']:>5} "
          f"net=${s['net']:>+9} maxDD=${s['maxDD']:>7} [{flag}]")
    return flag


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    results = {}
    if only in ("all", "dump"):
        ctxs15 = []
        missing = [s for s in ASSETS_15M
                   if not os.path.exists(os.path.join(DATA, f"{s}_15m.json"))]
        if missing:
            print(f"15m data missing for {missing} — run fetch_15m.py first; "
                  f"skipping 15m dump tests (NOT reporting n=0 as a result).")
        else:
            ctxs15 = [Ctx(load(s, "15m")) for s in ASSETS_15M]
            print(f"15m data: {ctxs15[0].n} bars/asset "
                  f"(2024-01-01 -> 2026-11-09, Binance.US)")
        for name, fn, size in [("DUMP_HEDGE_15", sig_dump_15, 0.30),
                               ("DOUBLE_PANIC", sig_double_panic, 0.30)]:
            if not ctxs15:
                continue
            trades = []
            for ctx in ctxs15:
                t, _ = simulate(ctx, fn, size_pct=size, max_hold=96)
                trades.extend(t)
            s = _stats(trades)
            results[name] = s
            _fmt(name, s)
    if only in ("all", "new1h"):
        ctxs1h = [Ctx(load(s, "1h")) for s in ASSETS_1H]
        print(f"1h data: {ctxs1h[0].n} bars/asset (2024-01-01 -> 2026-11-09)")
        for name, fn, size, cd in [("ECHO_TREND", sig_echo_trend, 1.0, 0),
                               ("ASCETIX_SPOT", sig_ascetix_spot, 0.25, 15)]:
            trades = []
            for ctx in ctxs1h:
                t, _ = simulate(ctx, fn, size_pct=size, max_hold=MAX_HOLD_BARS,
                                cooldown_bars=cd)
                trades.extend(t)
            s = _stats(trades)
            results[name] = s
            _fmt(name, s)
        all_t, test_t, Q = run_meta_learner(ctxs1h)
        s = _stats(all_t)
        results["META_LEARNER"] = s
        _fmt("META_LEARNER(all)", s)
        st = _stats(test_t)
        results["META_LEARNER_TEST"] = st
        _fmt("META_LEARNER(test)", st)
        print("  meta-learner Q-table (regime -> best strategy):")
        for reg, qs in Q.items():
            best = max(qs, key=lambda k: qs[k])
            print(f"    {reg:<11} best={best:<18} Q={qs[best]:+.3f}  "
                  f"all={ {k: round(v, 2) for k, v in qs.items()} }")
        by_strat = {}
        for t in all_t:
            by_strat.setdefault(t["strat"], []).append(t["pnl"])
        print("  meta-learner trades by chosen strategy:")
        for k, v in sorted(by_strat.items()):
            print(f"    {k:<18} n={len(v):>3} net=${sum(v):>+9.2f}")
    json.dump(results, open(os.path.join(HERE, "experiments_results.json"), "w"),
              indent=2)
    print("\nSaved experiments_results.json")


if __name__ == "__main__":
    main()

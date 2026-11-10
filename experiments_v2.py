"""experiments_v2.py — ApexGrid v2, 12-strategy stack.

Resume after Kevin's pause, on his order (2026-11-10): test 12, not 6.
Original 6 (Kevin's 3 + Plan B 3) plus 6 more (TrendRider, Turtle,
EMA Ribbon, Momentum rotation, Range trading, Volume breakout).

Paper / simulation ONLY. LIVE_MODE=False everywhere. No live trading,
no Kraken challenge, no entry fee, no GitHub push (report first).

Honest rules (v0 BREAKOUT lesson):
- Tune on 2024-2025, verify out-of-sample on 2026. Both reported.
- Two cost modes: HARD (10 bps/side + 5 bps slip = 0.30% RT) and
  KRAKEN (spread-only ~0.05% RT: 2 bps/side + 1 bp slip).
- Gates: expectancy > 0 after costs, PF > 1.2, n >= 100, maxDD <= $300
  on $10k paper capital.
- Long-only spot 1x throughout. No shorts (engine drops any short signal).
- Risk sizing: position sized so the stop-loss distance risks the stated
  % of $10k (e.g. 0.5% = $50), notional capped at $2,000/trade (cap
  disclosed per strategy if it binds).
- 5m data does NOT exist (only 15m/1h/4h Binance.US klines) — the EMA
  Ribbon scalp (spec 5m + 1m confirmation) is tested on 15m with the
  confirmation candle approximated on the same 15m bar. Disclosed.
- Session VWAP resets daily 00:00 UTC. Dynamic Grid is the re-centring
  variant only (v1 tested 12 classic variants, all benched except 2
  DD-failures). Kalman pairs uses a real Kalman-filter hedge ratio on
  log(BTC/ETH), long-only rotation adaptation (no short leg in spot).

Data: real Binance.US klines 2024-01-01 -> 2026-11-10 (1h 25,050 bars,
4h 6,263, 15m ~100,200). Split: train 2024-01-01..2025-12-31,
test 2026-01-01..2026-11-10 (first bar t >= 1767225600000).
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import LIVE_MODE, MAX_HOLD_BARS, NOTIONAL_PER_TRADE as NOTIONAL
from experiments import Ctx, load, _stats
from experiments_v1 import V1Ctx, load_v1
from indicators import rsi_wilder

assert LIVE_MODE is False
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
SPLIT_MS = 1767225600000  # 2026-01-01 00:00 UTC
PAPER = 10000.0


# ------------------------------------------------------------------ ADX
def _adx(df, period=14):
    """Wilder ADX(14), vectorized via ewm(alpha=1/period)."""
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    up = h - h.shift(1)
    dn = l.shift(1) - l
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr_s = pd.Series(tr).ewm(alpha=1 / period, adjust=False).mean()
    pdi = 100 * pd.Series(plus_dm).ewm(alpha=1 / period, adjust=False).mean() / atr_s.replace(0, np.nan)
    mdi = 100 * pd.Series(minus_dm).ewm(alpha=1 / period, adjust=False).mean() / atr_s.replace(0, np.nan)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean().to_numpy(dtype=float)


class V2Ctx(V1Ctx):
    def __init__(self, df):
        super().__init__(df)
        c = df["close"]
        self.ema8 = c.ewm(span=8, adjust=False).mean().to_numpy(dtype=float)
        self.ema9 = c.ewm(span=9, adjust=False).mean().to_numpy(dtype=float)
        self.ema20 = c.ewm(span=20, adjust=False).mean().to_numpy(dtype=float)
        self.ema21 = c.ewm(span=21, adjust=False).mean().to_numpy(dtype=float)
        self.ema55 = c.ewm(span=55, adjust=False).mean().to_numpy(dtype=float)
        self.sma5 = c.rolling(5).mean().to_numpy(dtype=float)
        self.sma10 = c.rolling(10).mean().to_numpy(dtype=float)
        self.rsi2 = rsi_wilder(c, period=2).to_numpy(dtype=float)
        self.adx = _adx(df)
        # Session VWAP (resets 00:00 UTC) + 2-sigma bands, from cumulative moments.
        tp = (df["high"] + df["low"] + df["close"]) / 3.0
        dates = pd.to_datetime(df["t"], unit="ms", utc=True).dt.date
        g = dates
        cum_pv = (tp * df["volume"]).groupby(g).cumsum()
        cum_v = df["volume"].groupby(g).cumsum()
        cum_pv2 = (tp * tp * df["volume"]).groupby(g).cumsum()
        vwap = (cum_pv / cum_v.replace(0, np.nan)).to_numpy(dtype=float)
        var = (cum_pv2 / cum_v.replace(0, np.nan)).to_numpy(dtype=float) - vwap ** 2
        std = np.sqrt(np.maximum(var, 0.0))
        self.vwap_sess = vwap
        self.vwap_up2 = vwap + 2 * std
        self.vwap_dn2 = vwap - 2 * std
        # split index: first bar on/after 2026-01-01
        t = df["t"].to_numpy(dtype=np.int64)
        idx = np.searchsorted(t, SPLIT_MS)
        self.split = int(idx)
        self.ts = t


def load_v2(symbol, tf="1h"):
    return V2Ctx(load(symbol, tf))


# ------------------------------------------------------------------ stats
def stats_split(trades):
    """Stats for a trade list, sorted chronologically by opened bar.
    Returns dict with n/win/exp/pf/net/maxDD. maxDD from the sorted
    equity curve (v1 pooled maxDD concatenated asset-by-asset, which
    is not a real equity curve — fixed here)."""
    if not trades:
        return dict(n=0, win=0.0, avgW=0.0, avgL=0.0, exp=0.0, pf=0.0, net=0.0, maxDD=0.0)
    s = _stats(sorted(trades, key=lambda t: t.get("bar", 0)))
    return s


def split_trades(trades, split):
    tr = [t for t in trades if t.get("bar", 0) < split]
    te = [t for t in trades if t.get("bar", 0) >= split]
    return tr, te


# ------------------------------------------------------------------ engine
def simulate_v2(ctx, sig_fn, fee_bps, slip_bps, risk_pct=0.005,
                max_hold=MAX_HOLD_BARS, cooldown_bars=0,
                notional_cap=2000.0, start=250, end=None):
    """Clean single-position engine, long-only, risk-sized.

    sig_fn(ctx, i) -> None | (side, tp, sl) | (side, tp, sl, opts).
    opts: {'trail_mult': ATR mult for trailing stop (uses entry ATR),
           'exit_below_lo': N (exit at close if close < min low last N),
           'ladder': [(min_hold_bars, tp_pct), ...] ROI ladder (TrendRider)}
    Fill at next bar open + slippage. TP/SL checked on bar high/low,
    SL first (as v0/v1). Fees charged as (entry+exit)*qty*fee_bps at exit.
    Position size: risk_dollars / |entry-sl|, capped at notional_cap.
    Short signals are DROPPED (long-only spot) and counted in the log.
    """
    fee = fee_bps / 10000.0
    slip = slip_bps / 10000.0
    n = ctx.n if end is None else min(end, ctx.n)
    trades = []
    pos = None
    pending = None
    last_entry = -10 ** 9
    dropped_short = 0
    for i in range(start, n - 1):
        o, h, l, cl = ctx.open[i], ctx.high[i], ctx.low[i], ctx.close[i]
        if pending is not None:
            side, tp, sl, opts = pending
            fill = o * (1 + slip)  # long only
            d = abs(fill - sl)
            risk_dollars = risk_pct * PAPER
            qty = risk_dollars / max(d, fill * 0.001)
            if qty * fill > notional_cap:
                qty = notional_cap / fill
            pos = dict(side="long", entry=fill, tp=tp, sl=sl, qty=qty,
                       opened=i, risk=risk_dollars, opts=opts,
                       atr_entry=opts.get("atr_entry", np.nan),
                       peak_close=fill, bar=i)
            pending = None
            last_entry = i
        if pos is not None:
            # trailing stop update (uses entry ATR, frozen)
            if pos["opts"].get("trail_mult") is not None and not np.isnan(pos["atr_entry"]):
                pos["peak_close"] = max(pos["peak_close"], cl)
                trail = pos["peak_close"] - pos["opts"]["trail_mult"] * pos["atr_entry"]
                pos["sl"] = max(pos["sl"], trail)
            # effective TP (ROI ladder: TP steps down with holding time)
            tp_eff = pos["tp"]
            ladder = pos["opts"].get("ladder")
            if ladder:
                age = i - pos["opened"]
                for min_hold, tp_pct in ladder:
                    if age >= min_hold:
                        tp_eff = pos["entry"] * (1 + tp_pct)
            exit_px, why = None, None
            if l <= pos["sl"]:
                exit_px, why = pos["sl"] * (1 - slip), "SL"
            elif h >= tp_eff:
                exit_px, why = tp_eff * (1 - slip), "TP"
            # Trend Assassin crowd exit: second volume spike while in profit
            if exit_px is None and pos["opts"].get("exit_vol_spike"):
                if (i - pos["opened"] >= 2 and cl > pos["entry"]
                        and not np.isnan(ctx.vol_avg[i])
                        and ctx.volume[i] > pos["opts"]["exit_vol_spike"] * ctx.vol_avg[i]):
                    exit_px, why = cl * (1 - slip), "CROWD"
            if exit_px is None and pos["opts"].get("exit_below_lo"):
                N = pos["opts"]["exit_below_lo"]
                if i >= N and cl < ctx.low[i - N:i].min():
                    exit_px, why = cl * (1 - slip), "LO10"
            if exit_px is None and i - pos["opened"] >= max_hold:
                exit_px, why = cl * (1 - slip), "TIME"
            if exit_px is not None:
                gross = (exit_px - pos["entry"]) * pos["qty"]
                fees = (pos["entry"] * pos["qty"] + exit_px * pos["qty"]) * fee
                trades.append(dict(pnl=round(gross - fees, 2), side="long", why=why,
                                   entry=round(pos["entry"], 4), exit=round(exit_px, 4),
                                   risk=round(pos["risk"], 2), bar=pos["bar"]))
                pos = None
        if pos is None and pending is None and i - last_entry >= cooldown_bars:
            sig = sig_fn(ctx, i)
            if sig is not None:
                if sig[0] != "long":
                    dropped_short += 1
                    continue
                side, tp, sl = sig[0], sig[1], sig[2]
                opts = dict(sig[3]) if len(sig) > 3 else {}
                if tp <= cl or sl >= cl or tp != tp or sl != sl:
                    continue  # invalid TP/SL vs entry — skip, do not trade
                pending = (side, tp, sl, opts)
    return trades, dropped_short


def run_strategy(ctxs, sig_fn, fee_bps, slip_bps, risk_pct=0.005,
                 max_hold=MAX_HOLD_BARS, cooldown_bars=0, asset_filter=None):
    """Run one signal fn across assets in both splits. Returns
    dict: {'train': stats, 'test': stats, 'all': stats, 'trades': [...]}.
    Trades carry 'bar' (opened bar index in that asset's frame) and
    'asset'. Split is per-asset (same calendar date, index may differ
    by 1 bar across tfs — each ctx carries its own split)."""
    all_trades, dropped = [], 0
    for ctx, sym in zip(ctxs, ASSETS):
        if asset_filter and sym not in asset_filter:
            continue
        tr, d = simulate_v2(ctx, sig_fn, fee_bps, slip_bps, risk_pct=risk_pct,
                            max_hold=max_hold, cooldown_bars=cooldown_bars)
        dropped += d
        for t in tr:
            t["asset"] = sym
        all_trades.extend(tr)
    # split per trade using its own asset's split index
    split_by_asset = {}
    for ctx, sym in zip(ctxs, ASSETS):
        split_by_asset[sym] = ctx.split
    tr = [t for t in all_trades if t["bar"] < split_by_asset[t["asset"]]]
    te = [t for t in all_trades if t["bar"] >= split_by_asset[t["asset"]]]
    return dict(train=stats_split(tr), test=stats_split(te),
                all=stats_split(all_trades), trades=all_trades,
                dropped_short=dropped)

# ============================================================ signals 1-6
# 1. Trend Following (Kevin) — 4h
def sig_trend_follow(ctx, i):
    if i < 250 or np.isnan(ctx.sma200[i]) or np.isnan(ctx.atr[i]):
        return None
    c = ctx.close[i]
    if c <= ctx.sma200[i]:
        return None
    hi20 = ctx.high[i - 20:i].max()  # prior 20 bars, excl. current
    if c <= hi20:
        return None
    if np.isnan(ctx.vol_avg[i]) or ctx.volume[i] <= ctx.vol_avg[i]:
        return None  # volume confirmation required by the spec
    a = ctx.atr[i]
    # TP far away (20%); exit is trailing stop / LO10 in the engine.
    return ("long", c * 1.20, c - 2.0 * a,
            {"trail_mult": 2.0, "atr_entry": a, "exit_below_lo": 10})


# 2. Pullback in Uptrend (Kevin) — 4h
def sig_pullback(ctx, i):
    if i < 250 or np.isnan(ctx.sma200[i]) or np.isnan(ctx.ema20[i]):
        return None
    c = ctx.close[i]
    if c <= ctx.sma200[i]:
        return None
    # dip in last 3 bars touched EMA20 or EMA50 (within 0.5%)
    dip = False
    for j in range(max(0, i - 2), i + 1):
        if ctx.low[j] <= ctx.ema20[j] * 1.005 or ctx.low[j] <= ctx.ema50[j] * 1.005:
            dip = True
    if not dip:
        return None
    # rejection candle: close in upper third, green, back above EMA20
    rng = ctx.high[i] - ctx.low[i]
    if rng <= 0 or c <= ctx.open[i] or c < ctx.low[i] + (2 / 3) * rng:
        return None
    if c < ctx.ema20[i]:
        return None
    dip_low = ctx.low[max(0, i - 2):i + 1].min()
    a = ctx.atr[i]
    if np.isnan(a):
        return None
    sl = dip_low - 0.2 * a
    if sl >= c:
        return None
    tp = c + 2.0 * (c - sl)  # 2:1, then trail (engine holds TP; no trail here)
    return ("long", tp, sl, {})


# 3. RSI(2) mean reversion, ranges only (Kevin) — 1h, BTC/ETH only
def sig_rsi2(ctx, i):
    if i < 250 or np.isnan(ctx.adx[i]) or np.isnan(ctx.sma200[i]):
        return None
    if ctx.adx[i] >= 20:
        return None  # ranging only
    if ctx.close[i] <= ctx.sma200[i]:
        return None
    if np.isnan(ctx.rsi2[i]) or ctx.rsi2[i] >= 10:
        return None
    c = ctx.close[i]
    tp = ctx.sma5[i]
    if np.isnan(tp) or tp <= c * 1.001:
        return None  # bounce target must be above entry
    sl = ctx.low[max(0, i - 4):i + 1].min() * 0.999
    if sl >= c:
        return None
    return ("long", tp, sl, {})


# 4a. VWAP Bounce (Plan B) — 15m, long only
def sig_vwap_bounce(ctx, i):
    if i < 250 or np.isnan(ctx.vwap_sess[i]) or np.isnan(ctx.vwap_dn2[i]):
        return None
    c = ctx.close[i]
    # price touched/pierced lower 2-sigma band, RSI<30, rejection candle
    if ctx.low[i] > ctx.vwap_dn2[i]:
        return None
    if np.isnan(ctx.rsi[i]) or ctx.rsi[i] >= 30:
        return None
    rng = ctx.high[i] - ctx.low[i]
    if rng <= 0 or c <= ctx.open[i] or c < ctx.low[i] + (2 / 3) * rng:
        return None
    tp = ctx.vwap_sess[i]
    if tp <= c * 1.001:
        return None
    sl = c * 0.99  # 1% SL (spec 0.8-1.2%)
    return ("long", tp, sl, {})


# 4b. VWAP Retest (Plan B) — 15m, long only
def sig_vwap_retest(ctx, i):
    if i < 250 or np.isnan(ctx.vwap_sess[i]):
        return None
    c = ctx.close[i]
    # breakout in last 10 bars: close > VWAP*1.01 with volume >1.5x avg
    broke = False
    for j in range(max(0, i - 10), i):
        if (ctx.close[j] > ctx.vwap_sess[j] * 1.01 and not np.isnan(ctx.vol_avg[j])
                and ctx.volume[j] > 1.5 * ctx.vol_avg[j]):
            broke = True
    if not broke:
        return None
    # pullback within 0.3% of VWAP + rejection candle
    if abs(c - ctx.vwap_sess[i]) / ctx.vwap_sess[i] > 0.003:
        return None
    rng = ctx.high[i] - ctx.low[i]
    if rng <= 0 or c <= ctx.open[i] or c < ctx.low[i] + (2 / 3) * rng:
        return None
    sl = ctx.low[max(0, i - 4):i + 1].min() * 0.999
    if sl >= c or (c - sl) / c > 0.008:
        return None  # spec SL 0.5-0.8%
    tp = c + 1.5 * (c - sl)
    return ("long", tp, sl, {})


# 5. Dynamic Grid — custom engine (see grid_dynamic below, not a signal fn)
# 6. Kalman pairs — custom engine (see pairs_kalman below, not a signal fn)


# ------------------------------------------------------- dynamic grid (5)
def grid_dynamic(ctx, fee_bps, slip_bps, spacing_pct=0.01, levels=5,
                 leg_notional=200.0, adx_gate=25.0, reset_bars=168,
                 start=250, end=None):
    """Re-centring grid (Chen et al. DGT, arXiv 2506.11921), adapted:
    - Anchor at first bar; buy levels at anchor*(1-k*spacing), sell a lot
      one level up. One lot per level.
    - When price exits the range (above top / below bottom level): RESET
      the centre to current price and KEEP open lots (hold below the
      lower bound instead of dumping them — the DGT difference).
    - Re-anchor also every reset_bars.
    - Buys gated to ADX < adx_gate (range only).
    - maxDD from the equity curve (realised + unrealised mark-to-close).
    Trades carry 'bar' = close bar (for train/test split).
    start/end: run on a sub-range ONLY, closing all lots at `end`.
    This matters: a grid's realised trades are mostly wins (losing lots
    are held unrealised), so pooling realised trades across a split
    gives a fake PF (999) and $0 DD. The honest split runs the grid
    separately on train and on test, realising everything at the
    boundary. Never pool realised grid trades across the split."""
    fee = fee_bps / 10000.0
    slip = slip_bps / 10000.0
    end = ctx.n if end is None else min(end, ctx.n)
    trades = []
    lots = []
    anchor = None
    anchor_bar = 0
    equity, peak, mdd = 0.0, 0.0, 0.0

    def mark(i):
        return sum((ctx.close[i] - lot["entry"]) * lot["qty"] for lot in lots)

    for i in range(start, end):
        c = ctx.close[i]
        if anchor is None:
            anchor = c
            anchor_bar = i
            continue
        # range exit or time: re-anchor, KEEP lots (DGT hold)
        top = anchor * (1 + levels * spacing_pct)
        bot = anchor * (1 - levels * spacing_pct)
        if c >= top or c <= bot or i - anchor_bar >= reset_bars:
            anchor = c
            anchor_bar = i
        # sell lots that reached one level up
        for lot in list(lots):
            target = anchor * (1 - (lot["level_k"] - 1) * spacing_pct) \
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
        peak = max(peak, equity + mark(i))
        mdd = max(mdd, peak - (equity + mark(i)))
        # buy unfilled levels below price, ADX-gated
        if np.isnan(ctx.adx[i]) or ctx.adx[i] >= adx_gate:
            continue
        for k in range(1, levels + 1):
            lvl = anchor * (1 - k * spacing_pct)
            if c <= lvl and not any(lot["level_k"] == k and lot.get("anchor") == anchor
                                    for lot in lots):
                fill = c * (1 + slip)
                qty = leg_notional / fill
                lots.append(dict(level_k=k, entry=fill, qty=qty, anchor=anchor,
                                 target=anchor * (1 - (k - 1) * spacing_pct)))
    if lots:
        c = ctx.close[end - 1]
        for lot in lots:
            exit_px = c * (1 - slip)
            gross = (exit_px - lot["entry"]) * lot["qty"]
            fees = (lot["entry"] * lot["qty"] + exit_px * lot["qty"]) * fee
            pnl = round(gross - fees, 2)
            trades.append(dict(pnl=pnl, side="grid-close", entry=round(lot["entry"], 2),
                               exit=round(exit_px, 2), bar=end - 1))
            equity += pnl
    s = stats_split(trades)
    s["maxDD"] = round(max(mdd, s["maxDD"]), 2)
    return s, trades


# ------------------------------------------------------- Kalman pairs (6)
def pairs_kalman(ctx_btc, ctx_eth, fee_bps, slip_bps, risk_pct=0.005):
    """BTC/ETH Kalman pairs, long-only rotation adaptation.
    Kalman filter on beta in logBTC = beta * logETH + spread; spread
    z-scored on a 50-bar rolling mean/std. z>=+2: ETH cheap -> long ETH.
    z<=-2: BTC cheap -> long BTC. Exit at z~0, SL at |z|>=3.5, max 100 bars.
    Fixed $1,000 notional (risk sizing needs a spread-implied SL, which
    does not map cleanly to a single-asset stop — disclosed)."""
    fee = fee_bps / 10000.0
    slip = slip_bps / 10000.0
    lb, le = np.log(ctx_btc.close), np.log(ctx_eth.close)
    n = min(len(lb), len(le))
    beta = np.full(n, 1.0)
    b, P = 1.0, 1.0
    Q, R = 0.001, 0.01
    spread = np.full(n, np.nan)
    for i in range(n):
        x, y = le[i], lb[i]
        # predict (beta persists), update
        K = P * x / (x * x * P + R)
        b = b + K * (y - b * x)
        P = (1 - K * x) * P + Q
        beta[i] = b
        spread[i] = y - b * x
    s = pd.Series(spread)
    mu = s.rolling(50).mean().to_numpy(dtype=float)
    sd = s.rolling(50).std().to_numpy(dtype=float)
    z = (spread - mu) / sd
    trades = []
    pos = None
    pending = None
    for i in range(250, n - 1):
        if np.isnan(z[i]):
            continue
        if pending is not None:
            asset, ctx = pending
            o = ctx.open[i]
            fill = o * (1 + slip)
            qty = NOTIONAL / fill
            pos = dict(asset=asset, ctx=ctx, entry=fill, qty=qty, opened=i, bar=i)
            pending = None
        if pos is not None:
            ctx = pos["ctx"]
            c = ctx.close[i]
            exit_px, why = None, None
            if abs(z[i]) < 0.1:
                exit_px, why = c * (1 - slip), "Z0"
            elif abs(z[i]) >= 3.5:
                exit_px, why = c * (1 - slip), "ZSL"
            elif i - pos["opened"] >= 100:
                exit_px, why = c * (1 - slip), "TIME"
            if exit_px is not None:
                gross = (exit_px - pos["entry"]) * pos["qty"]
                fees = (pos["entry"] * pos["qty"] + exit_px * pos["qty"]) * fee
                trades.append(dict(pnl=round(gross - fees, 2), side="long", why=why,
                                   entry=round(pos["entry"], 4), exit=round(exit_px, 4),
                                   asset=pos["asset"], bar=pos["bar"]))
                pos = None
        if pos is None and pending is None:
            if z[i] >= 2.0:
                pending = ("ETHUSDT", ctx_eth)
            elif z[i] <= -2.0:
                pending = ("BTCUSDT", ctx_btc)
    return trades

# ============================================================ signals 7-13
# 7. TrendRider multi-confirmation trend (Plan B Rank 1) — 1h
def sig_trendrider(ctx, i):
    if i < 250 or np.isnan(ctx.ema8[i]) or np.isnan(ctx.macd[i]):
        return None
    if np.isnan(ctx.rsi[i]) or ctx.rsi[i] >= 70:
        return None
    if ctx.macd[i] <= ctx.macd_sig[i]:
        return None
    # EMA8 crosses above EMA21 this bar
    if not (ctx.ema8[i] > ctx.ema21[i] and ctx.ema8[i - 1] <= ctx.ema21[i - 1]):
        return None
    c = ctx.close[i]
    a = ctx.atr[i]
    if np.isnan(a):
        return None
    # ROI ladder: +5% now, +2.5% after 30 bars, +1% after 60 bars.
    # Initial SL -3%; trailing 2x ATR in the engine.
    return ("long", c * 1.05, c * 0.97,
            {"ladder": [(0, 0.05), (30, 0.025), (60, 0.01)],
             "trail_mult": 2.0, "atr_entry": a})


# 8a. Turtle / Donchian 20/10 breakout (Plan B Rank 5) — 4h
def _turtle(ctx, i, tp_1r=False):
    if i < 250 or np.isnan(ctx.atr[i]):
        return None
    c = ctx.close[i]
    hi20 = ctx.high[i - 20:i].max()
    if c <= hi20:
        return None
    a = ctx.atr[i]
    sl = c - 2.0 * a
    tp = c + 2.0 * a if tp_1r else c * 1.20  # 1:1 variant vs far TP + LO10 exit
    return ("long", tp, sl, {"exit_below_lo": 10})


def sig_turtle(ctx, i):
    return _turtle(ctx, i, tp_1r=False)


def sig_turtle_tp1(ctx, i):
    return _turtle(ctx, i, tp_1r=True)


# 9. EMA Ribbon pullback scalp (Plan B Rank 6) — 15m proxy for 5m
#    (no 5m data; 1m confirmation approximated on the same 15m bar)
def sig_ema_ribbon(ctx, i):
    if i < 250 or np.isnan(ctx.ema55[i]):
        return None
    # ribbon stacked long
    if not (ctx.ema9[i] > ctx.ema21[i] > ctx.ema55[i]):
        return None
    # pullback: low touched 21 EMA (within 0.05%), close back above it
    if ctx.low[i] > ctx.ema21[i] * 1.0005 or ctx.close[i] < ctx.ema21[i]:
        return None
    # confirmation: bullish candle, close in upper half
    rng = ctx.high[i] - ctx.low[i]
    if rng <= 0 or ctx.close[i] <= ctx.open[i]:
        return None
    if ctx.close[i] < ctx.low[i] + 0.5 * rng:
        return None
    c = ctx.close[i]
    sl = ctx.ema55[i] * 0.9995
    if sl >= c:
        return None
    tp = c * 1.004  # 0.4% TP (spec 0.3-0.5%)
    return ("long", tp, sl, {})


# 11. Range trading (Kevin) — 1h
def sig_range(ctx, i):
    if i < 250 or np.isnan(ctx.adx[i]):
        return None
    if ctx.adx[i] >= 20:
        return None  # ranging only; turn OFF when a range breaks / trends
    hi20 = ctx.high[i - 20:i].max()
    lo20 = ctx.low[i - 20:i].min()
    c = ctx.close[i]
    if (hi20 - lo20) / c > 0.04:
        return None  # range too wide to be a range
    if c > lo20 * 1.01:
        return None  # only buy range lows
    if c < lo20:
        return None  # already below the range low = range broken down, not a buy
    if hi20 <= c * 1.005:
        return None
    sl = lo20 * 0.995
    return ("long", hi20, sl, {"exit_below_lo": 20})


# 12. Breakout with volume confirmation (Kevin) — 1h
def sig_vol_breakout(ctx, i):
    if i < 250 or np.isnan(ctx.vol_avg[i]) or np.isnan(ctx.atr[i]):
        return None
    hi20 = ctx.high[i - 20:i].max()
    lo20 = ctx.low[i - 20:i].min()
    c = ctx.close[i]
    # consolidation: 20-bar range < 3%
    if (hi20 - lo20) / c > 0.03:
        return None
    if c <= hi20:
        return None
    if ctx.volume[i] <= ctx.vol_avg[i]:
        return None  # low-volume breakouts skipped (spec: above 20-bar avg)
    a = ctx.atr[i]
    return ("long", c + 2.5 * a, c - 1.5 * a, {})


# 13. Trend Assassin (Gravia Prime) — 1h, long only
def sig_trend_assassin_v2(ctx, i):
    """Trend at BIRTH: velocity + volume together. Exit on the CROWD:
    a second volume spike while in profit, or trailing 2x ATR, or -2% SL."""
    if i < 250 or np.isnan(ctx.sma200[i]) or np.isnan(ctx.vol_avg[i]):
        return None
    c = ctx.close[i]
    if c <= ctx.sma200[i]:
        return None
    if ctx.close[i - 1] <= 0 or (c / ctx.close[i - 1] - 1) <= 0.015:
        return None  # need a >1.5% up close
    if ctx.volume[i] <= 2.0 * ctx.vol_avg[i]:
        return None  # volume spike must arrive WITH the velocity
    a = ctx.atr[i]
    if np.isnan(a):
        return None
    return ("long", c * 1.20, c * 0.98,  # far TP; exit is crowd / trail / SL
            {"trail_mult": 2.0, "atr_entry": a, "exit_vol_spike": 2.0})


# 14. Mean reversion, classic z-score (Kevin) — 1h, BTC/ETH only
def sig_mean_rev_zscore(ctx, i):
    if i < 250 or np.isnan(ctx.adx[i]) or np.isnan(ctx.sma20[i]):
        return None
    if ctx.adx[i] >= 25:
        return None  # ranging only — never trade this in a strong trend
    if np.isnan(ctx.rsi[i]) or ctx.rsi[i] >= 30:
        return None
    sd20 = ctx.close[i - 20:i].std()
    if sd20 is None or np.isnan(sd20) or sd20 <= 0:
        return None
    z = (ctx.close[i] - ctx.sma20[i]) / sd20
    if z >= -2.0:
        return None  # need >2 SD below the 20-period mean
    c = ctx.close[i]
    tp = ctx.sma20[i]
    if tp <= c * 1.001:
        return None
    # SL below the recent low, capped at -1.5% max loss distance
    sl = max(ctx.low[max(0, i - 4):i + 1].min() * 0.999, c * 0.985)
    if sl >= c:
        return None
    return ("long", tp, sl, {})


# ------------------------------------------------------- momentum rotation (10)
def momentum_rotation(ctxs, fee_bps, slip_bps, lookback_bars=1440, rebalance_bars=168):
    """Rank BTC/ETH/SOL by 60-day (1440 x 1h bars) return, hold the leader
    if its return > 0, else cash (USDC). Rebalance every 168 bars (weekly).
    $1,000 notional per week so PnL is comparable to the other arms.
    Switch cost = round-trip fee+slip on $1,000. Each invested week is
    one 'trade' (bar = rebalance index)."""
    cost_rt = (2 * fee_bps + 2 * slip_bps) / 10000.0
    trades = []
    # rebalance indices: every 168 bars from the first usable bar
    start = max(lookback_bars + 1, 250)
    n = min(ctx.n for ctx in ctxs)
    current = None  # asset symbol held, or None for cash
    entry_px = None
    entry_bar = None
    for i in range(start, n - rebalance_bars, rebalance_bars):
        rets = {}
        for ctx, sym in zip(ctxs, ASSETS):
            if i >= lookback_bars and ctx.close[i - lookback_bars] > 0:
                rets[sym] = ctx.close[i] / ctx.close[i - lookback_bars] - 1
        best = max(rets, key=rets.get) if rets else None
        target = best if (best is not None and rets[best] > 0) else None
        # close the outgoing week
        if current is not None:
            ctx = dict(zip(ASSETS, ctxs))[current]
            exit_px = ctx.close[i]
            gross = (exit_px - entry_px) / entry_px * NOTIONAL
            cost = NOTIONAL * cost_rt if target != current else 0.0
            # cost is charged on the switch (exit+entry); if staying, 0
            trades.append(dict(pnl=round(gross - cost, 2), side="long",
                               asset=current, bar=entry_bar, ts=int(ctx.ts[i])))
            current, entry_px, entry_bar = None, None, None
        if target is not None:
            ctx = dict(zip(ASSETS, ctxs))[target]
            current, entry_px, entry_bar = target, ctx.close[i], i
    if current is not None:
        ctx = dict(zip(ASSETS, ctxs))[current]
        exit_px = ctx.close[-1]
        gross = (exit_px - entry_px) / entry_px * NOTIONAL
        trades.append(dict(pnl=round(gross - NOTIONAL * cost_rt, 2), side="long",
                           asset=current, bar=entry_bar,
                           ts=int(ctx.ts[-1])))
    return trades


# ------------------------------------------------------------------ runner
def _fmt(name, mode, s_train, s_test):
    def flag(s):
        return "PASS" if (s["exp"] > 0 and s["pf"] > 1.2 and s["n"] >= 100 and s["maxDD"] <= 300) else "fail"
    print(f"{name:<22} {mode:<6} TRAIN n={s_train['n']:>5} exp=${s_train['exp']:>+6} "
          f"PF={s_train['pf']:>5} net=${s_train['net']:>+9} DD=${s_train['maxDD']:>7} | "
          f"TEST n={s_test['n']:>5} exp=${s_test['exp']:>+6} PF={s_test['pf']:>5} "
          f"net=${s_test['net']:>+9} DD=${s_test['maxDD']:>7} [{flag(s_test)} test-gate]")


def _split_stats_for_trades(trades, ctxs):
    split_by = {sym: ctx.split for ctx, sym in zip(ctxs, ASSETS)}
    # rotation/pairs trades carry 'asset'; grid trades get asset set by caller
    tr = [t for t in trades if t.get("bar", 0) < split_by.get(t.get("asset", ASSETS[0]), 10 ** 9)]
    te = [t for t in trades if t.get("bar", 0) >= split_by.get(t.get("asset", ASSETS[0]), 10 ** 9)]
    return stats_split(tr), stats_split(te)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    results = {}
    ctxs = {}
    for tf in ("1h", "4h", "15m"):
        ctxs[tf] = [load_v2(s, tf) for s in ASSETS]
        print(f"{tf} data: {ctxs[tf][0].n} bars/asset, split@{ctxs[tf][0].split} "
              f"(2026-01-01), test bars={ctxs[tf][0].n - ctxs[tf][0].split}")
    # (name, tf, sig_fn, risk_pct, max_hold, asset_filter)
    SINGLE = [
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
    modes = {"hard": (10.0, 5.0), "kraken": (2.0, 1.0)}
    passing = {}  # mode -> list of (name, trades)
    for mode, (fb, sb) in modes.items():
        passing[mode] = []
        for name, tf, fn, risk, mh, filt in SINGLE:
            if only != "all" and only not in name.lower():
                continue
            r = run_strategy(ctxs[tf], fn, fb, sb, risk_pct=risk, max_hold=mh,
                             asset_filter=filt)
            # attach timestamps for stacking
            ts_by = {sym: ctx.ts for ctx, sym in zip(ctxs[tf], ASSETS)}
            for t in r["trades"]:
                t["ts"] = int(ts_by[t["asset"]][t["bar"]])
            results[f"{name}__{mode}"] = dict(train=r["train"], test=r["test"],
                                              all=r["all"], dropped_short=r["dropped_short"])
            _fmt(name, mode, r["train"], r["test"])
            if r["test"]["exp"] > 0 and r["test"]["pf"] > 1.2 and r["test"]["n"] >= 30 \
                    and r["test"]["maxDD"] <= 300 and r["all"]["n"] >= 100:
                passing[mode].append((name, r["trades"]))
        # --- custom engines, same mode ---
        # Dynamic grid (1h): run SEPARATELY on train and on test, closing
        # all lots at the split boundary. Pooling realised grid trades
        # across the split gives a fake PF=999 / $0 DD (see grid_dynamic
        # docstring). Per-run equity-curve DD is kept; pooled DD is the
        # worst single-asset equity DD (conservative).
        g_train_tr, g_test_tr = [], []
        g_train_dd = g_test_dd = 0.0
        for ctx, sym in zip(ctxs["1h"], ASSETS):
            s_tr, tr_tr = grid_dynamic(ctx, fb, sb, start=250, end=ctx.split)
            s_te, tr_te = grid_dynamic(ctx, fb, sb, start=ctx.split, end=ctx.n)
            for t in tr_tr:
                t["asset"] = sym
                t["ts"] = int(ctx.ts[min(t["bar"], ctx.n - 1)])
            for t in tr_te:
                t["asset"] = sym
                t["ts"] = int(ctx.ts[min(t["bar"], ctx.n - 1)])
            g_train_tr.extend(tr_tr)
            g_test_tr.extend(tr_te)
            g_train_dd = max(g_train_dd, s_tr["maxDD"])
            g_test_dd = max(g_test_dd, s_te["maxDD"])
        g_train = stats_split(g_train_tr)
        g_train["maxDD"] = round(max(g_train_dd, g_train["maxDD"]), 2)
        g_test = stats_split(g_test_tr)
        g_test["maxDD"] = round(max(g_test_dd, g_test["maxDD"]), 2)
        g_all = stats_split(g_train_tr + g_test_tr)
        g_all["maxDD"] = round(max(g_train_dd, g_test_dd, g_all["maxDD"]), 2)
        results[f"DYN_GRID_1H__{mode}"] = dict(train=g_train, test=g_test, all=g_all)
        _fmt("DYN_GRID_1H", mode, g_train, g_test)
        if g_test["exp"] > 0 and g_test["pf"] > 1.2 and g_test["n"] >= 30 \
                and g_test["maxDD"] <= 300 and g_all["n"] >= 100:
            passing[mode].append(("DYN_GRID_1H", g_train_tr + g_test_tr))
        # Kalman pairs (1h BTC/ETH)
        p_trades = pairs_kalman(ctxs["1h"][0], ctxs["1h"][1], fb, sb)
        ts_map = {"BTCUSDT": ctxs["1h"][0].ts, "ETHUSDT": ctxs["1h"][1].ts}
        for t in p_trades:
            t["ts"] = int(ts_map[t["asset"]][t["bar"]])
        p_train, p_test = _split_stats_for_trades(p_trades, ctxs["1h"])
        p_all = stats_split(p_trades)
        results[f"KALMAN_PAIRS_1H__{mode}"] = dict(train=p_train, test=p_test, all=p_all)
        _fmt("KALMAN_PAIRS_1H", mode, p_train, p_test)
        if p_test["exp"] > 0 and p_test["pf"] > 1.2 and p_test["n"] >= 30 \
                and p_test["maxDD"] <= 300 and p_all["n"] >= 100:
            passing[mode].append(("KALMAN_PAIRS_1H", p_trades))
        # Momentum rotation (1h, weekly)
        m_trades = momentum_rotation(ctxs["1h"], fb, sb)
        # rotation trades carry ts already; bar is rebalance index (1h frame)
        m_train, m_test = _split_stats_for_trades(m_trades, ctxs["1h"])
        m_all = stats_split(m_trades)
        results[f"MOMENTUM_ROT_1H__{mode}"] = dict(train=m_train, test=m_test, all=m_all)
        _fmt("MOMENTUM_ROT_1H", mode, m_train, m_test)
        if m_test["exp"] > 0 and m_test["pf"] > 1.2 and m_test["n"] >= 30 \
                and m_test["maxDD"] <= 300 and m_all["n"] >= 100:
            passing[mode].append(("MOMENTUM_ROT_1H", m_trades))
        # --- stacked swarm: only passing strategies, chronological equity ---
        stack = []
        for nm, tr in passing[mode]:
            stack.extend(tr)
        stack_sorted = sorted(stack, key=lambda t: t.get("ts", 0))
        eq, peak, mdd = 0.0, 0.0, 0.0
        for t in stack_sorted:
            eq += t["pnl"]
            peak = max(peak, eq)
            mdd = max(mdd, peak - eq)
        s_all = stats_split(stack_sorted)
        s_all["maxDD"] = round(max(mdd, s_all["maxDD"]), 2)
        results[f"STACK_PASSING__{mode}"] = dict(
            members=[nm for nm, _ in passing[mode]], all=s_all, maxDD_chron=mdd)
        print(f"STACK ({mode}): members={[nm for nm, _ in passing[mode]]} "
              f"n={s_all['n']} net=${s_all['net']} maxDD_chron=${round(mdd, 2)} "
              f"Kraken target +$1,200 / DD <=$300")
    json.dump(results, open(os.path.join(HERE, "experiments_v2_results.json"), "w"), indent=2)
    print("\nSaved experiments_v2_results.json")


if __name__ == "__main__":
    main()

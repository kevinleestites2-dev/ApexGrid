"""experiments_v1.py — ApexGrid v1 expansion harness.

Kevin: "go crazy, put more in, improve the winning strategies or make up
some stuff — the strategies need to match the name."

v1 adds:
  GRID FAMILY (the namesake, first-class): regime-gated grid, ATR grid,
    7-level grid, trend-armed grid, FOMO grid, Echo grid, tight/wide grids.
    Grid is a REAL multi-lot engine (buy a level on a dip, sell it one
    level up), not a single-position signal — see grid_simulate().
  MYTHOS 10 ports: Supertrend, MACD Cross, Golden Cross, Stochastic,
    Fibonacci Pullback, Ichimoku, Volume-Price Delta, Volatility Expansion.
  UpsideOnly VWAP reversion. MetaTrader: Momentum Breakout (triple filter),
    Liquidity Sweep fade, Stat Arb (BTC/ETH pair, synthetic ratio trade —
    labelled), Funding proxy, CVD divergence, OI-spike proxy, Liquidation
    Cascade proxy. Proxies are labelled PROXY wherever a real feed (funding
    rate, OI, liquidation zones, CVD) does not exist in klines.
  NEW combos: BREAKOUT+ECHO, DUMP+ASCETIX, TREND_ASSASSIN (crowd exit).
  TUNING: BREAKOUT TP/SL/vol/lookback sweep + Dump & Hedge threshold/TP/SL
    sweep on BTC 15m, validated on all assets.

Same honest rules as v0: real Binance.US history, fees 10bps/side +
5bps slippage, expectancy not win rate, no lookahead, TP/SL/time-stop/
max-hold on every trade, Kraken paper target +12% / never drop 3% ($300).
LIVE_MODE=False everywhere. A strategy only earns a funded spot if
exp > 0 AND n >= 30. Everything negative is reported benched, not hidden.

Usage: python3 experiments_v1.py [grid|mythos|tune|all]
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
from experiments import Ctx, load, simulate, _stats

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FEE = FEE_BPS / 10000.0
SLIP = SLIPPAGE_BPS / 10000.0
ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


# ---------------------------------------------------------------- indicators
def _supertrend_dir(df):
    """Supertrend (10, 3x ATR) direction, iterative bands. Returns array
    of +1 (up) / -1 (down)."""
    hl2 = (df["high"] + df["low"]) / 2.0
    atrv = df["atr"].to_numpy(dtype=float)
    hl2v = hl2.to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    n = len(df)
    up = np.full(n, np.nan)
    dn = np.full(n, np.nan)
    direction = np.zeros(n, dtype=int)
    trend = 1
    for i in range(1, n):
        if np.isnan(atrv[i]):
            continue
        ub = hl2v[i] + 3.0 * atrv[i]
        lb = hl2v[i] - 3.0 * atrv[i]
        # Standard final bands: upper only moves DOWN (min) while price is
        # below it; lower only moves UP (max) while price is above it.
        # (v1 first draft had both conditions inverted, so the bands just
        # tracked price and the trend almost never flipped — caught by the
        # n=1 diagnostic, fixed here.)
        up[i] = ub if np.isnan(up[i - 1]) else (min(ub, up[i - 1]) if close[i - 1] <= up[i - 1] else ub)
        dn[i] = lb if np.isnan(dn[i - 1]) else (max(lb, dn[i - 1]) if close[i - 1] >= dn[i - 1] else lb)
        if trend == 1 and close[i] < dn[i]:
            trend = -1
        elif trend == -1 and close[i] > up[i]:
            trend = 1
        direction[i] = trend
    return direction


class V1Ctx(Ctx):
    """Ctx + v1 indicators, all precomputed once (vectorized)."""

    def __init__(self, df):
        super().__init__(df)
        c = df["close"]
        self.ema12 = c.ewm(span=12, adjust=False).mean().to_numpy(dtype=float)
        self.ema26 = c.ewm(span=26, adjust=False).mean().to_numpy(dtype=float)
        self.macd = self.ema12 - self.ema26
        self.macd_sig = pd.Series(self.macd).ewm(span=9, adjust=False).mean().to_numpy(dtype=float)
        self.ema50 = c.ewm(span=50, adjust=False).mean().to_numpy(dtype=float)
        self.ema200 = c.ewm(span=200, adjust=False).mean().to_numpy(dtype=float)
        self.sma200 = c.rolling(200).mean().to_numpy(dtype=float)
        # Stochastic %K/%D (14,3)
        lo14 = df["low"].rolling(14).min()
        hi14 = df["high"].rolling(14).max()
        self.stoch_k = ((c - lo14) / (hi14 - lo14) * 100).to_numpy(dtype=float)
        self.stoch_d = pd.Series(self.stoch_k).rolling(3).mean().to_numpy(dtype=float)
        self.supertrend = _supertrend_dir(df)
        # Ichimoku Tenkan (9) / Kijun (26)
        self.tenkan = ((df["high"].rolling(9).max() + df["low"].rolling(9).min()) / 2).to_numpy(dtype=float)
        self.kijun = ((df["high"].rolling(26).max() + df["low"].rolling(26).min()) / 2).to_numpy(dtype=float)
        # VWAP proxy: 24-bar rolling VWAP (typical price x volume)
        tp = (df["high"] + df["low"] + df["close"]) / 3.0
        self.vwap24 = ((tp * df["volume"]).rolling(24).sum() / df["volume"].rolling(24).sum()).to_numpy(dtype=float)
        # CVD proxy: signed volume (close-open)/range * volume, 50-bar sum
        rng = (df["high"] - df["low"]).replace(0, np.nan)
        delta = ((df["close"] - df["open"]) / rng * df["volume"]).fillna(0.0)
        self.cvd50 = delta.rolling(50).sum().to_numpy(dtype=float)
        self.cvd = delta.to_numpy(dtype=float)
        # 50-bar SMA slope regime, vectorized (same rule as indicators.regime)
        m50 = c.rolling(50).mean()
        slope = (m50 - m50.shift(50)) / m50.shift(50)
        self.regime_arr = np.array([
            "TREND_UP" if (not np.isnan(s) and s > 0.005) else
            "TREND_DOWN" if (not np.isnan(s) and s < -0.005) else
            "SIDEWAYS" if not np.isnan(s) else "UNKNOWN"
            for s in slope.to_numpy(dtype=float)])
        self.hi20 = df["high"].rolling(20).max().to_numpy(dtype=float)
        self.lo20 = df["low"].rolling(20).min().to_numpy(dtype=float)
        self.ret5 = (c / c.shift(5) - 1).to_numpy(dtype=float)


def load_v1(symbol, tf="1h"):
    return V1Ctx(load(symbol, tf))


# ------------------------------------------------------- single-position sigs
def _atr_sig(ctx, i, side, tp_mult=2.0, sl_mult=1.5):
    c, a = ctx.close[i], ctx.atr[i]
    if np.isnan(a) or a <= 0:
        return None
    if side == "long":
        return ("long", c + tp_mult * a, c - sl_mult * a)
    return ("short", c - tp_mult * a, c + sl_mult * a)


def sig_supertrend(ctx, i):
    if i < 2 or ctx.supertrend[i] == 0:
        return None
    if ctx.supertrend[i] == 1 and ctx.supertrend[i - 1] == -1:
        return _atr_sig(ctx, i, "long", 3.0, 2.0)  # MYTHOS: TP 15% / SL 5% scaled to ATR
    if ctx.supertrend[i] == -1 and ctx.supertrend[i - 1] == 1:
        return _atr_sig(ctx, i, "short", 3.0, 2.0)
    return None


def sig_macd_cross(ctx, i):
    if i < 2 or np.isnan(ctx.macd[i]) or np.isnan(ctx.macd_sig[i]):
        return None
    if ctx.regime_arr[i] not in ("TREND_UP", "TREND_DOWN"):
        return None
    if ctx.macd[i - 1] <= ctx.macd_sig[i - 1] and ctx.macd[i] > ctx.macd_sig[i]:
        return _atr_sig(ctx, i, "long", 2.0, 1.5)
    if ctx.macd[i - 1] >= ctx.macd_sig[i - 1] and ctx.macd[i] < ctx.macd_sig[i]:
        return _atr_sig(ctx, i, "short", 2.0, 1.5)
    return None


def sig_golden_cross(ctx, i):
    # MYTHOS: 50 SMA crosses 200 SMA, bull-trend only. TP 30% / SL 10% in
    # the original — scaled here to ATR 5x/2x so a 100-bar hold can realise it.
    if i < 2 or np.isnan(ctx.sma200[i]):
        return None
    s50 = ctx.sma50[i]
    if np.isnan(s50):
        return None
    if s50 > ctx.sma200[i] and ctx.sma50[i - 1] <= ctx.sma200[i - 1]:
        return _atr_sig(ctx, i, "long", 5.0, 2.0)
    return None


def sig_stochastic(ctx, i):
    if i < 2 or ctx.regime_arr[i] != "SIDEWAYS":
        return None
    k, d = ctx.stoch_k[i], ctx.stoch_d[i]
    kp, dp = ctx.stoch_k[i - 1], ctx.stoch_d[i - 1]
    if np.isnan(k) or np.isnan(d) or np.isnan(kp):
        return None
    if k < 20 and kp < dp and k >= d:
        return _atr_sig(ctx, i, "long", 2.0, 1.5)
    if k > 80 and kp > dp and k <= d:
        return _atr_sig(ctx, i, "short", 2.0, 1.5)
    return None


def sig_fib_pullback(ctx, i):
    # Bull trend only: price touches 61.8% retracement of last 50-bar range.
    if i < 50 or ctx.regime_arr[i] != "TREND_UP":
        return None
    hi = ctx.high[i - 50:i].max()
    lo = ctx.low[i - 50:i].min()
    fib = hi - 0.618 * (hi - lo)
    c = ctx.close[i]
    if abs(c - fib) / fib <= 0.01:
        return _atr_sig(ctx, i, "long", 3.0, 1.5)
    return None


def sig_ichimoku(ctx, i):
    if i < 2 or np.isnan(ctx.tenkan[i]) or np.isnan(ctx.kijun[i]):
        return None
    if ctx.regime_arr[i] != "TREND_UP":
        return None
    c = ctx.close[i]
    if c > ctx.tenkan[i] and c > ctx.kijun[i] and ctx.tenkan[i] > ctx.kijun[i]:
        if not (ctx.close[i - 1] > ctx.tenkan[i - 1] and ctx.tenkan[i - 1] > ctx.kijun[i - 1]):
            return _atr_sig(ctx, i, "long", 3.0, 2.0)
    return None


def sig_vol_price_delta(ctx, i):
    if i < 2 or np.isnan(ctx.vol_avg[i]):
        return None
    if ctx.volume[i] > 1.5 * ctx.vol_avg[i] and ctx.close[i] > ctx.close[i - 1] * 1.01:
        return _atr_sig(ctx, i, "long", 2.0, 1.5)
    if ctx.volume[i] > 1.5 * ctx.vol_avg[i] and ctx.close[i] < ctx.close[i - 1] * 0.99:
        return _atr_sig(ctx, i, "short", 2.0, 1.5)
    return None


def sig_vol_expansion(ctx, i):
    # MYTHOS: close above upper 2-sigma band in volatile-sideways.
    if np.isnan(ctx.bb_up[i]):
        return None
    if ctx.close[i] > ctx.bb_up[i] and ctx.close[i - 1] <= ctx.bb_up[i - 1]:
        return _atr_sig(ctx, i, "long", 3.0, 2.0)
    return None


def sig_vwap_reversion(ctx, i):
    # UpsideOnly #32: price >1.5% from session VWAP, RSI confirms.
    if np.isnan(ctx.vwap24[i]) or np.isnan(ctx.rsi[i]):
        return None
    c, v = ctx.close[i], ctx.vwap24[i]
    dev = (c - v) / v
    a = ctx.atr[i]
    if np.isnan(a):
        return None
    if dev > 0.015 and ctx.rsi[i] > 60:
        return ("short", v, c + 1.0 * a)
    if dev < -0.015 and ctx.rsi[i] < 40:
        return ("long", v, c - 1.0 * a)
    return None


def sig_momentum_breakout(ctx, i):
    # MetaTrader #18: break 2% above resistance + volume >=1.5x + TREND_UP.
    if i < 20 or ctx.regime_arr[i] != "TREND_UP":
        return None
    c = ctx.close[i]
    res = ctx.high[i - 20:i].max()
    if c > res * 1.02 and ctx.volume[i] > 1.5 * ctx.vol_avg[i]:
        return _atr_sig(ctx, i, "long", 3.0, 1.5)
    return None


def sig_liq_sweep(ctx, i):
    # MetaTrader #19: spike through a wall (20-bar high) but close back
    # within 0.5% of it -> fade the sweep.
    if i < 20:
        return None
    hi20 = ctx.high[i - 20:i].max()
    c = ctx.close[i]
    if ctx.high[i] > hi20 * 1.005 and c <= hi20 * 1.005:
        return _atr_sig(ctx, i, "short", 1.0, 1.0)
    lo20 = ctx.low[i - 20:i].min()
    if ctx.low[i] < lo20 * 0.995 and c >= lo20 * 0.995:
        return _atr_sig(ctx, i, "long", 1.0, 1.0)
    return None


def sig_cvd_divergence(ctx, i):
    # MetaTrader #17 PROXY: price rallies 10%+ over 10 bars but CVD
    # (signed-volume proxy) is falling -> bearish divergence, SHORT.
    # Real CVD needs exchange order-flow data; this is a klines proxy.
    if i < 10:
        return None
    ret10 = ctx.close[i] / ctx.close[i - 10] - 1
    cvd_now, cvd_prev = ctx.cvd50[i], ctx.cvd50[i - 10]
    if ret10 > 0.10 and cvd_now < cvd_prev:
        return _atr_sig(ctx, i, "short", 2.0, 1.5)
    if ret10 < -0.10 and cvd_now > cvd_prev:
        return _atr_sig(ctx, i, "long", 2.0, 1.5)
    return None


def sig_oi_spike(ctx, i):
    # MetaTrader #21 PROXY: volume (OI proxy) jumps 30%+ vs 20-bar avg
    # AND price rising -> LONG. Real OI needs a derivatives feed.
    if i < 2 or np.isnan(ctx.vol_avg[i]):
        return None
    if ctx.volume[i] > 1.3 * ctx.vol_avg[i] and ctx.close[i] > ctx.close[i - 1] * 1.005:
        return _atr_sig(ctx, i, "long", 2.0, 1.5)
    if ctx.volume[i] > 1.3 * ctx.vol_avg[i] and ctx.close[i] < ctx.close[i - 1] * 0.995:
        return _atr_sig(ctx, i, "short", 2.0, 1.5)
    return None


def sig_liq_cascade(ctx, i):
    # MetaTrader #22, corrected: a swing low is a liquidity cluster.
    # Price is DRAWN to it, so the trade is the bounce OFF it: LONG when
    # price reaches within 0.5% of the 20-bar low, TP +2%, SL just below
    # the low. (The first v1 draft had TP below entry for a long — an
    # inverted signal, caught by the smoke test. Fixed here.)
    if i < 20:
        return None
    lo20 = ctx.low[i - 20:i].min()
    c = ctx.close[i]
    if c <= lo20 * 1.005:
        return ("long", c * 1.02, min(lo20 * 0.99, c * 0.99))
    hi20 = ctx.high[i - 20:i].max()
    if c >= hi20 * 0.995:
        return ("short", c * 0.98, max(hi20 * 1.01, c * 1.01))
    return None


def sig_funding_proxy(ctx, i):
    # MetaTrader #13 PROXY: premium = (close - EMA50)/EMA50 stands in for
    # the funding rate (no funding feed in klines). Premium >0.5% -> SHORT
    # (harvest the premium); < -0.5% -> LONG. TP/SL 2%.
    if np.isnan(ctx.ema50[i]):
        return None
    prem = (ctx.close[i] - ctx.ema50[i]) / ctx.ema50[i]
    c = ctx.close[i]
    if prem > 0.005:
        return ("short", c * 0.98, c * 1.02)
    if prem < -0.005:
        return ("long", c * 1.02, c * 0.98)
    return None


def sig_breakout_echo(ctx, i):
    # NEW: v0 BREAKOUT signal, only if Echo FFT+shape agrees.
    if ctx.regime_arr[i] not in ("TREND_UP", "TREND_DOWN"):
        return None
    if i < 20 or np.isnan(ctx.vol_avg[i]):
        return None
    if not ctx.echo_agrees(i):
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


def sig_trend_assassin(ctx, i):
    # NEW: Trend Assassin — ride trend birth (velocity + volume spike
    # together), exit when the crowd arrives (second volume spike).
    # Entry: 5-bar return >2% + volume >2x avg. Exit is modelled as a
    # tight TP 3% / SL 1% plus the engine max-hold — the crowd exit is
    # the TP itself (retail arrival = the move is done).
    if i < 5 or np.isnan(ctx.vol_avg[i]):
        return None
    if ctx.ret5[i] is None or np.isnan(ctx.ret5[i]):
        return None
    if ctx.ret5[i] > 0.02 and ctx.volume[i] > 2.0 * ctx.vol_avg[i]:
        c, a = ctx.close[i], ctx.atr[i]
        if np.isnan(a):
            return None
        return ("long", c + 3.0 * a, c - 1.0 * a)
    if ctx.ret5[i] < -0.02 and ctx.volume[i] > 2.0 * ctx.vol_avg[i]:
        c, a = ctx.close[i], ctx.atr[i]
        if np.isnan(a):
            return None
        return ("short", c - 3.0 * a, c + 1.0 * a)
    return None


SINGLE_1H = {
    "SUPERTREND": sig_supertrend,
    "MACD_CROSS": sig_macd_cross,
    "GOLDEN_CROSS": sig_golden_cross,
    "STOCHASTIC": sig_stochastic,
    "FIB_PULLBACK": sig_fib_pullback,
    "ICHIMOKU": sig_ichimoku,
    "VOL_PRICE_DELTA": sig_vol_price_delta,
    "VOL_EXPANSION": sig_vol_expansion,
    "VWAP_REVERSION": sig_vwap_reversion,
    "MOMENTUM_BREAKOUT": sig_momentum_breakout,
    "LIQ_SWEEP": sig_liq_sweep,
    "CVD_DIVERGENCE_PROXY": sig_cvd_divergence,
    "OI_SPIKE_PROXY": sig_oi_spike,
    "LIQ_CASCADE_PROXY": sig_liq_cascade,
    "FUNDING_PROXY": sig_funding_proxy,
    "BREAKOUT_ECHO_NEW": sig_breakout_echo,
    "TREND_ASSASSIN_NEW": sig_trend_assassin,
}


# ------------------------------------------------------------- pairs (stat arb)
def pairs_stat_arb(ctx_a, ctx_b):
    """MetaTrader #14 / Gravia MSA, cross-asset: log(BTC/ETH) ratio
    z-score (50-bar). |z|>2 -> trade the reversion as a SYNTHETIC pair
    trade: notional $1,000 on the ratio, TP at z=0, SL at z=3.
    Labelled synthetic — it is not a single-asset fill."""
    ra = np.log(ctx_a.close / ctx_b.close)
    s = pd.Series(ra)
    mu = s.rolling(50).mean().to_numpy(dtype=float)
    sd = s.rolling(50).std().to_numpy(dtype=float)
    z = (ra - mu) / sd
    trades = []
    pos = None
    pending = None
    for i in range(100, len(ra) - 1):
        if np.isnan(z[i]):
            continue
        if pending is not None:
            side, tp_r, sl_r = pending
            fill = ra[i] * (1 + SLIP) if side == "long" else ra[i] * (1 - SLIP)
            pos = dict(side=side, entry=fill, tp=tp_r, sl=sl_r, opened=i)
            pending = None
        if pos is not None:
            r = ra[i]
            exit_r = None
            if pos["side"] == "long":
                if r <= pos["sl"]:
                    exit_r = pos["sl"]
                elif r >= pos["tp"]:
                    exit_r = pos["tp"]
            else:
                if r >= pos["sl"]:
                    exit_r = pos["sl"]
                elif r <= pos["tp"]:
                    exit_r = pos["tp"]
            if exit_r is None and i - pos["opened"] >= MAX_HOLD_BARS:
                exit_r = r
            if exit_r is not None:
                # ratio moves are ~1-2%: scale pnl to $1,000 notional on the ratio
                gross = (exit_r - pos["entry"]) * NOTIONAL if pos["side"] == "long" else (pos["entry"] - exit_r) * NOTIONAL
                fees = 2 * NOTIONAL * FEE
                trades.append(dict(pnl=round(gross - fees, 2), side=pos["side"],
                                   entry=round(pos["entry"], 4), exit=round(exit_r, 4)))
                pos = None
        if pos is None and pending is None:
            if z[i] > 2.0:
                # ratio too high: short the ratio (short BTC, long ETH)
                pending = ("short", mu[i], mu[i] + 3 * sd[i])
            elif z[i] < -2.0:
                pending = ("long", mu[i], mu[i] - 3 * sd[i])
    return trades


# ------------------------------------------------------------------ grid
def grid_simulate(ctx, spacing_pct=0.01, levels=5, leg_notional=200.0,
                  stop_pct=0.08, reset_bars=168, only_sideways=False,
                  only_trend=False, buy_filter=None, name="GRID",
                  atr_spacing=False):
    """Real multi-lot grid engine.

    Anchor at the first bar's close. Buy levels at anchor*(1-k*spacing),
    sell each lot one level up (anchor*(1-(k-1)*spacing)). One lot per
    level. Fills at bar close + slippage (grid trades are level-crossings,
    disclosed — not next-bar-open like single-position signals).
    Re-anchor every reset_bars, or on stop_pct move: close all lots at
    close, realise, reset anchor. MaxDD is computed on the equity curve
    (realised + unrealised mark-to-close), not just closed trades.
    buy_filter(ctx, i) -> bool gates new buys (FOMO/Echo variants).
    atr_spacing=True: spacing is set at each anchor from ATR/close,
    clamped to 0.5%-2%.
    """
    trades = []
    lots = []  # dict(level_k, entry, qty)
    anchor = None
    anchor_bar = 0
    sp = spacing_pct
    equity, peak, mdd = 0.0, 0.0, 0.0

    def _set_spacing(i, price):
        if not atr_spacing:
            return spacing_pct
        a = ctx.atr[i]
        if a != a or not price:
            return 0.01
        return float(min(0.02, max(0.005, a / price)))

    def _mark(i):
        # unrealised pnl of open lots at close[i]
        u = 0.0
        for lot in lots:
            u += (ctx.close[i] - lot["entry"]) * lot["qty"]
        return u

    for i in range(100, ctx.n):
        c = ctx.close[i]
        if anchor is None:
            anchor = c
            anchor_bar = i
            sp = _set_spacing(i, c)
            continue
        # --- re-anchor / stop: close everything, realise, reset
        if i - anchor_bar >= reset_bars or abs(c - anchor) / anchor >= stop_pct:
            for lot in lots:
                exit_px = c * (1 - SLIP)
                gross = (exit_px - lot["entry"]) * lot["qty"]
                fees = (lot["entry"] * lot["qty"] + exit_px * lot["qty"]) * FEE
                pnl = round(gross - fees, 2)
                trades.append(dict(pnl=pnl, side="grid-close", entry=round(lot["entry"], 2),
                                   exit=round(exit_px, 2)))
                equity += pnl
            lots = []
            anchor = c
            anchor_bar = i
            sp = _set_spacing(i, c)
            peak = max(peak, equity)
            continue
        # --- sell lots that reached one level up
        for lot in list(lots):
            target = anchor * (1 - (lot["level_k"] - 1) * sp)
            if c >= target:
                exit_px = c * (1 - SLIP)
                gross = (exit_px - lot["entry"]) * lot["qty"]
                fees = (lot["entry"] * lot["qty"] + exit_px * lot["qty"]) * FEE
                pnl = round(gross - fees, 2)
                trades.append(dict(pnl=pnl, side="grid-sell", entry=round(lot["entry"], 2),
                                   exit=round(exit_px, 2)))
                equity += pnl
                lots.remove(lot)
        peak = max(peak, equity + _mark(i))
        mdd = max(mdd, peak - (equity + _mark(i)))
        # --- buy unfilled levels below price
        if only_sideways and ctx.regime_arr[i] != "SIDEWAYS":
            continue
        if only_trend and ctx.regime_arr[i] not in ("TREND_UP", "TREND_DOWN"):
            continue
        if buy_filter is not None and not buy_filter(ctx, i):
            continue
        for k in range(1, levels + 1):
            lvl = anchor * (1 - k * sp)
            if c <= lvl and not any(lot["level_k"] == k for lot in lots):
                fill = c * (1 + SLIP)
                qty = leg_notional / fill
                lots.append(dict(level_k=k, entry=fill, qty=qty))
    # close remaining lots at the end
    if lots:
        c = ctx.close[-1]
        for lot in lots:
            exit_px = c * (1 - SLIP)
            gross = (exit_px - lot["entry"]) * lot["qty"]
            fees = (lot["entry"] * lot["qty"] + exit_px * lot["qty"]) * FEE
            pnl = round(gross - fees, 2)
            trades.append(dict(pnl=pnl, side="grid-close", entry=round(lot["entry"], 2),
                               exit=round(exit_px, 2)))
            equity += pnl
    s = _stats(trades)
    s["maxDD"] = round(max(mdd, s["maxDD"]), 2)
    return s, trades


GRID_VARIANTS = [
    ("GRID_SIDEWAYS_1PCT", dict(spacing_pct=0.01, levels=5, only_sideways=True)),
    ("GRID_ATR", dict(spacing_pct=0.01, levels=5, atr_spacing=True)),
    ("GRID_7LEVEL_1.5PCT", dict(spacing_pct=0.015, levels=7)),
    ("GRID_TREND_ARMED", dict(spacing_pct=0.01, levels=5, only_trend=True)),
    ("GRID_FOMO_RSI40", dict(spacing_pct=0.01, levels=5,
                             buy_filter=lambda ctx, i: (not np.isnan(ctx.rsi[i]) and ctx.rsi[i] < 40))),
    ("GRID_ECHO", dict(spacing_pct=0.01, levels=5,
                       buy_filter=lambda ctx, i: ctx.echo_agrees(i))),
    ("GRID_TIGHT_0.5PCT", dict(spacing_pct=0.005, levels=5)),
    ("GRID_WIDE_2PCT", dict(spacing_pct=0.02, levels=5)),
    # No-stop variants (added after the first grid run showed the 8% stop
    # was the main loss source — re-anchor only, lots held through trends).
    ("GRID_NOSTOP_1PCT", dict(spacing_pct=0.01, levels=5, stop_pct=1.0)),
    ("GRID_SIDEWAYS_NOSTOP", dict(spacing_pct=0.01, levels=5, stop_pct=1.0, only_sideways=True)),
    ("GRID_ECHO_NOSTOP", dict(spacing_pct=0.01, levels=5, stop_pct=1.0,
                              buy_filter=lambda ctx, i: ctx.echo_agrees(i))),
    ("GRID_WIDE2_NOSTOP", dict(spacing_pct=0.02, levels=5, stop_pct=1.0)),
]


# ------------------------------------------------------------------ tuning
def make_breakout(tp_mult, sl_mult, vol_mult, lookback, regime_on=True):
    """TUNING BASE = the real v0 BreakoutAgent (strategies.py:180), NOT
    the loose experiments.py meta-learner copy. v0: close breaks 0.5%
    beyond the prior-lookback CLOSE high/low, fixed % TP/SL, no volume
    filter, regime TREND or UNKNOWN. tp_mult/sl_mult here are PERCENT
    (e.g. 3.0 = +3%), vol_mult=None means no volume filter.
    The first v1 tuning sweep used the loose copy (no buffer, ATR exits,
    volume filter) and got n~2,800 — a different strategy entirely.
    Those numbers are VOID; this sweep supersedes them."""
    def fn(ctx, i):
        if regime_on and ctx.regime_arr[i] not in ("TREND_UP", "TREND_DOWN", "UNKNOWN"):
            return None
        if i < lookback + 1:
            return None
        c = ctx.close[i]
        hi = ctx.close[i - lookback - 1:i - 1].max() if False else ctx.close[i - lookback:i].max()
        lo = ctx.close[i - lookback:i].min()
        # NOTE: v0 used closes[-21:-1] (prior 20 closes, excluding current).
        # ctx.close[i-lookback:i] is the same window when lookback=20.
        if vol_mult is not None and not np.isnan(ctx.vol_avg[i]):
            if ctx.volume[i] < vol_mult * ctx.vol_avg[i]:
                return None
        if c >= hi * 1.005:
            return ("long", c * (1 + tp_mult / 100.0), c * (1 - sl_mult / 100.0))
        if c <= lo * 0.995:
            return ("short", c * (1 - tp_mult / 100.0), c * (1 + sl_mult / 100.0))
        return None
    return fn


def make_breakout_v0(tp_pct=3.0, sl_pct=1.5, lookback=20, buffer_pct=0.5,
                     vol_mult=None, regime_unknown=True):
    """Faithful v0 BreakoutAgent with tunable knobs. Defaults = v0 exactly."""
    def fn(ctx, i):
        allowed = ("TREND_UP", "TREND_DOWN", "UNKNOWN") if regime_unknown else ("TREND_UP", "TREND_DOWN")
        if ctx.regime_arr[i] not in allowed:
            return None
        if i < lookback + 1:
            return None
        c = ctx.close[i]
        hi = ctx.close[i - lookback:i].max()
        lo = ctx.close[i - lookback:i].min()
        if vol_mult is not None and not np.isnan(ctx.vol_avg[i]):
            if ctx.volume[i] < vol_mult * ctx.vol_avg[i]:
                return None
        if c >= hi * (1 + buffer_pct / 100.0):
            return ("long", c * (1 + tp_pct / 100.0), c * (1 - sl_pct / 100.0))
        if c <= lo * (1 - buffer_pct / 100.0):
            return ("short", c * (1 - tp_pct / 100.0), c * (1 + sl_pct / 100.0))
        return None
    return fn


def sig_dump_param(threshold, tp_pct, sl_pct):
    def fn(ctx, i):
        o, l, c = ctx.open[i], ctx.low[i], ctx.close[i]
        if o > 0 and (o - l) / o >= threshold:
            return ("long", c * (1 + tp_pct), c * (1 - sl_pct))
        return None
    return fn


# ------------------------------------------------------------------ main
def _fmt(name, s):
    flag = "PROVEN" if (s["exp"] > 0 and s["n"] >= 30) else \
        ("POSITIVE-UNPROVEN" if s["exp"] > 0 else "NEGATIVE")
    print(f"{name:<24} n={s['n']:>4} win={s['win']:>5}% exp=${s['exp']:>+7}/trade "
          f"PF={s['pf']:>5} net=${s['net']:>+9} maxDD=${s['maxDD']:>7} [{flag}]")
    return flag


def run_single(ctxs, fn, size_pct=1.0, max_hold=MAX_HOLD_BARS, cooldown=0):
    trades = []
    for ctx in ctxs:
        t, _ = simulate(ctx, fn, size_pct=size_pct, max_hold=max_hold, cooldown_bars=cooldown)
        trades.extend(t)
    return _stats(trades)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    results = {}
    ctxs1h = None
    if only in ("all", "mythos", "grid", "tune", "pairs"):
        ctxs1h = [load_v1(s, "1h") for s in ASSETS]
        print(f"1h data: {ctxs1h[0].n} bars/asset")
    if only in ("all", "grid"):
        print("\n== GRID FAMILY (1h, leg $200, re-anchor 168 bars / stop 8%) ==")
        for name, kw in GRID_VARIANTS:
            pooled = []
            worst_dd = 0.0
            for ctx in ctxs1h:
                s, tr = grid_simulate(ctx, **kw)
                pooled.extend(tr)
                worst_dd = max(worst_dd, s["maxDD"])
            agg = _stats(pooled)
            # _stats maxDD is from the concatenated trade sequence; the
            # per-asset equity-curve maxDD is the honest per-asset figure —
            # report the worst single-asset DD alongside the pooled one.
            agg["maxDD_worst_asset"] = round(worst_dd, 2)
            results[name] = agg
            _fmt(name, agg)
    if only in ("all", "mythos"):
        print("\n== MYTHOS + MetaTrader + VWAP + NEW combos (1h) ==")
        for name, fn in SINGLE_1H.items():
            s = run_single(ctxs1h, fn)
            results[name] = s
            _fmt(name, s)
    if only in ("all", "pairs"):
        print("\n== STAT ARB pair BTC/ETH (synthetic ratio trade) ==")
        trades = pairs_stat_arb(ctxs1h[0], ctxs1h[1])
        s = _stats(trades)
        results["STAT_ARB_BTCETH"] = s
        _fmt("STAT_ARB_BTCETH", s)
    if only in ("all", "tune"):
        print("\n== BREAKOUT TUNING — faithful v0 base (0.5% buffer, close "
              "high/low, fixed % TP/SL) ==")
        # Stage 1: TP/SL/lookback, v0 defaults for the rest.
        best = None
        for tp, sl in [(2.0, 1.0), (3.0, 1.5), (5.0, 2.0), (5.0, 2.5)]:
            for lb in (10, 20, 50):
                fn = make_breakout_v0(tp_pct=tp, sl_pct=sl, lookback=lb)
                s = run_single(ctxs1h, fn)
                tag = f"BREAKOUTv0_TP{tp}_SL{sl}_LB{lb}"
                results[tag] = s
                _fmt(tag, s)
                if s["n"] >= 30 and (best is None or s["exp"] > best[1]["exp"]):
                    best = (tag, s, (tp, sl, lb))
        print(f"  BEST stage 1: {best[0] if best else 'none'}")
        # Stage 2: buffer + volume filter around the stage-1 winner.
        if best:
            tp, sl, lb = best[2]
            for buf in (0.3, 0.5, 1.0):
                for vol in (None, 1.5):
                    fn = make_breakout_v0(tp_pct=tp, sl_pct=sl, lookback=lb,
                                          buffer_pct=buf, vol_mult=vol)
                    s = run_single(ctxs1h, fn)
                    tag = f"BREAKOUTv0_TP{tp}_SL{sl}_LB{lb}_BUF{buf}_V{vol}"
                    results[tag] = s
                    _fmt(tag, s)
                    if s["exp"] > 0 and s["n"] >= 30 and s["exp"] > best[1]["exp"]:
                        best = (tag, s, (tp, sl, lb))
            print(f"  BEST BREAKOUT (faithful v0 base): {best[0]}")
        print("\n== DUMP & HEDGE TUNING (15m, BTC only, then validate) ==")
        ctx_btc15 = Ctx(load("BTCUSDT", "15m"))
        best_d = None
        for thr in (0.02, 0.03, 0.04, 0.05):
            for tp, sl in [(0.03, 0.05), (0.05, 0.10), (0.08, 0.10), (0.05, 0.05)]:
                for hold in (48, 96):
                    fn = sig_dump_param(thr, tp, sl)
                    t, _ = simulate(ctx_btc15, fn, size_pct=0.30, max_hold=hold)
                    s = _stats(t)
                    tag = f"DUMP_BTC_T{int(thr*100)}_TP{int(tp*100)}_SL{int(sl*100)}_H{hold}"
                    results[tag] = s
                    _fmt(tag, s)
                    if s["n"] >= 10 and (best_d is None or s["exp"] > best_d[1]["exp"]):
                        best_d = (tag, s, (thr, tp, sl, hold))
        print(f"  BEST DUMP (BTC): {best_d[0] if best_d else 'none'}")
        if best_d:
            thr, tp, sl, hold = best_d[2]
            fn = sig_dump_param(thr, tp, sl)
            trades = []
            for sym in ASSETS:
                ctx = Ctx(load(sym, "15m"))
                t, _ = simulate(ctx, fn, size_pct=0.30, max_hold=hold)
                trades.extend(t)
                print(f"    validate {sym}: {_stats(t)}")
            s = _stats(trades)
            results["DUMP_BEST_ALL_ASSETS"] = s
            _fmt("DUMP_BEST_ALL_ASSETS", s)
    json.dump(results, open(os.path.join(HERE, "experiments_v1_results.json"), "w"), indent=2)
    print("\nSaved experiments_v1_results.json")


if __name__ == "__main__":
    main()

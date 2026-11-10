"""Indicators — boring, tested math only. Stdlib + pandas/numpy."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (exponential smoothing), as in UpsideOnly signal_engine."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=True).mean()
    loss = -delta.clip(upper=0).ewm(com=period - 1, adjust=True).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return (df["high"] - df["low"]).rolling(period).mean()


def bollinger(close: pd.Series, period: int = 20, std: float = 2.0):
    sma = close.rolling(period).mean()
    sd = close.rolling(period).std()
    return sma + std * sd, sma, sma - std * sd


def sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def avg_volume(volume: pd.Series, period: int = 20) -> pd.Series:
    return volume.rolling(period).mean()


def regime(df: pd.DataFrame, i: int) -> str:
    """MYTHOS-style regime gate: trend by 50-bar SMA slope.
    Compares the 50-bar SMA ending at bar i with the 50-bar SMA ending
    50 bars earlier — a real slope over 50 bars. (The previous version
    compared two 50-bar means ONE bar apart, which moves ~0.02%/bar, so
    the 0.5% threshold almost never fired and 99.9% of bars read
    SIDEWAYS — that bug benched BREAKOUT and ECHO in the first 1h run.)
    Returns TREND_UP / TREND_DOWN / SIDEWAYS / UNKNOWN (not enough bars)."""
    if i < 100 or len(df) <= i:
        return "UNKNOWN"
    sma_now = df["close"].iloc[i - 50:i].mean()
    sma_prev = df["close"].iloc[i - 100:i - 50].mean()
    if sma_prev == 0:
        return "UNKNOWN"
    slope = (sma_now - sma_prev) / sma_prev
    if slope > 0.005:
        return "TREND_UP"
    if slope < -0.005:
        return "TREND_DOWN"
    return "SIDEWAYS"

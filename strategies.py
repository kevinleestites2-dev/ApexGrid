"""
Strategy agents — one per strategy, plain __init__ (no lambda-tuple trick;
that is what killed Gravia-Prime on startup).

Each agent is stateless except for its own risk counters. tick() receives
the bar history up to the current bar (no future data — no lookahead) and
returns a Signal or None. The backtest engine owns positions, TP/SL,
execution at the next bar's open, and ledger recording.

Signal: dataclass with direction, entry (current close), tp, sl, confidence.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pandas as pd

from config import (
    FOMO_LOSS_LIMIT, FOMO_MAX_CONSEC_LOSSES, FOMO_SL, FOMO_TIME_STOP_BARS,
    FOMO_TP,
)
from indicators import atr, avg_volume, bollinger, regime, rsi_wilder


@dataclass
class Signal:
    strategy: str
    symbol: str
    direction: str  # "long" or "short"
    entry_price: float
    tp_price: float
    sl_price: float
    confidence: float
    time_stop_bars: int = 0  # 0 = no time stop


class Agent:
    """Base agent. __init__ returns None, always — boring on purpose."""

    name = "base"

    def __init__(self) -> None:
        self.consec_losses = 0
        self.recent_pnls: list[float] = []

    def tick(self, symbol: str, df: pd.DataFrame, breadth: float = 0.0) -> Signal | None:
        raise NotImplementedError

    def note_outcome(self, pnl: float) -> None:
        self.recent_pnls.append(pnl)
        self.recent_pnls = self.recent_pnls[-6:]
        self.consec_losses = self.consec_losses + 1 if pnl <= 0 else 0


# ---------------------------------------------------------------- FOMO/PANIC
class FomoPanicAgent(Agent):
    """S28 FOMO & PANIC — contrarian emotion fader (design doc).

    4-signal composite, 3-of-4 confirms. Shorts FOMO tops, longs PANIC
    bottoms. Sentiment is the swarm breadth proxy: fraction of the universe
    moving in the same direction this bar (the recovered code read sentiment
    off the INTEL_BUS; v0 has no live bus, so breadth is the honest proxy
    and is labelled as such in the report).
    Original: RSI 78/22, 3x volume, 1.5% velocity, TP 2.5%, SL 1%,
    10-bar time stop, 3-loss breaker, $300 loss limit.
    """
    name = "FOMO_PANIC"

    def tick(self, symbol: str, df: pd.DataFrame, breadth: float = 0.0) -> Signal | None:
        if len(df) < 50:
            return None
        # Circuit breakers first.
        if self.consec_losses >= FOMO_MAX_CONSEC_LOSSES:
            return None
        if sum(p for p in self.recent_pnls if p < 0) <= -FOMO_LOSS_LIMIT:
            return None
        close = df["close"]
        rsi = rsi_wilder(close).iloc[-1]
        vol = df["volume"].iloc[-1]
        vol_avg = avg_volume(df["volume"]).iloc[-1]
        velocity = (close.iloc[-1] / close.iloc[-2] - 1.0) if len(close) > 1 else 0.0
        if pd.isna(rsi) or pd.isna(vol_avg) or vol_avg == 0:
            return None
        price = float(close.iloc[-1])
        # FOMO top: RSI overbought, volume spike, up velocity, bullish breadth.
        fomo_votes = sum([
            rsi >= 78,
            vol >= 3 * vol_avg,
            velocity >= 0.015,
            breadth >= 0.66,
        ])
        panic_votes = sum([
            rsi <= 22,
            vol >= 3 * vol_avg,
            velocity <= -0.015,
            breadth <= -0.66,
        ])
        if fomo_votes >= 3:
            return Signal(self.name, symbol, "short", price,
                          price * (1 - FOMO_TP), price * (1 + FOMO_SL),
                          0.60 + 0.1 * (fomo_votes - 3),
                          time_stop_bars=FOMO_TIME_STOP_BARS)
        if panic_votes >= 3:
            return Signal(self.name, symbol, "long", price,
                          price * (1 + FOMO_TP), price * (1 - FOMO_SL),
                          0.60 + 0.1 * (panic_votes - 3),
                          time_stop_bars=FOMO_TIME_STOP_BARS)
        return None


# ------------------------------------------------------- RSI mean reversion
class RsiMeanReversionAgent(Agent):
    """UpsideOnly #30: RSI>=72 short, RSI<=28 long, ATR exits, R:R>=1.5,
    confidence>=0.60 double-gate.
    FIX vs the original: the original used TP 2.0xATR / SL 1.5xATR, which
    gives R:R = 2.0/1.5 = 1.33 ALWAYS — below its own 1.5 gate, so the
    original agent could never fire a single trade (verified: 0 trades
    in the first 4h backtest run). v0 uses TP 2.5xATR, R:R = 1.67.
    MYTHOS regime gate: fires in SIDEWAYS regimes only."""
    name = "RSI_MEAN_REVERSION"

    def tick(self, symbol: str, df: pd.DataFrame, breadth: float = 0.0) -> Signal | None:
        if len(df) < 50:
            return None
        if regime(df, len(df) - 1) not in ("SIDEWAYS", "UNKNOWN"):
            return None
        close = df["close"]
        rsi = rsi_wilder(close).iloc[-1]
        a = atr(df).iloc[-1]
        price = float(close.iloc[-1])
        if pd.isna(rsi) or pd.isna(a) or a == 0:
            return None
        if rsi >= 72:
            sl, tp = price + 1.5 * a, price - 2.5 * a
            rr = (price - tp) / (sl - price)
            conf = min(0.95, 0.60 + ((rsi - 72) / 28) * 0.35)
            if rr >= 1.5 and conf >= 0.60:
                return Signal(self.name, symbol, "short", price, tp, sl, conf)
        elif rsi <= 28:
            sl, tp = price - 1.5 * a, price + 2.5 * a
            rr = (tp - price) / (price - sl)
            conf = min(0.95, 0.60 + ((28 - rsi) / 28) * 0.35)
            if rr >= 1.5 and conf >= 0.60:
                return Signal(self.name, symbol, "long", price, tp, sl, conf)
        return None


# ------------------------------------------------------------ Bollinger fade
class BollingerFadeAgent(Agent):
    """UpsideOnly #31: close beyond 2-sigma band + RSI confirms, TP at mid-band.
    MYTHOS regime gate: fires in SIDEWAYS regimes only."""
    name = "BOLLINGER_FADE"

    def tick(self, symbol: str, df: pd.DataFrame, breadth: float = 0.0) -> Signal | None:
        if len(df) < 50:
            return None
        if regime(df, len(df) - 1) not in ("SIDEWAYS", "UNKNOWN"):
            return None
        close = df["close"]
        upper, mid, lower = bollinger(close)
        rsi = rsi_wilder(close).iloc[-1]
        a = atr(df).iloc[-1]
        price = float(close.iloc[-1])
        if pd.isna(upper.iloc[-1]) or pd.isna(rsi) or pd.isna(a):
            return None
        if price > upper.iloc[-1] and rsi > 65:
            return Signal(self.name, symbol, "short", price,
                          float(mid.iloc[-1]), price + 1.2 * a,
                          min(0.9, 0.60 + (rsi - 65) / 100))
        if price < lower.iloc[-1] and rsi < 35:
            return Signal(self.name, symbol, "long", price,
                          float(mid.iloc[-1]), price - 1.2 * a,
                          min(0.9, 0.60 + (35 - rsi) / 100))
        return None


# ------------------------------------------------------------------ Breakout
class BreakoutAgent(Agent):
    """OpenAgora #33, completed: 20-candle high/low break +-0.5%.
    Original was signal-only (no exits) — v0 adds TP 3% / SL 1.5%.
    MYTHOS regime gate: fires in TREND regimes only."""
    name = "BREAKOUT"

    def tick(self, symbol: str, df: pd.DataFrame, breadth: float = 0.0) -> Signal | None:
        if len(df) < 50:
            return None
        if regime(df, len(df) - 1) not in ("TREND_UP", "TREND_DOWN", "UNKNOWN"):
            return None
        close = df["close"]
        price = float(close.iloc[-1])
        hi = close.iloc[-21:-1].max()
        lo = close.iloc[-21:-1].min()
        if price >= hi * 1.005:
            conf = min(1.0, 0.60 + (price / hi - 1.0) * 10)
            return Signal(self.name, symbol, "long", price,
                          price * 1.03, price * 0.985, conf)
        if price <= lo * 0.995:
            conf = min(1.0, 0.60 + (1.0 - price / lo) * 10)
            return Signal(self.name, symbol, "short", price,
                          price * 0.97, price * 1.015, conf)
        return None


# ------------------------------------------------------------- Q-learning
class QLearningAgent(Agent):
    """OpenAgora #35, rebuilt. Fixes vs the original:
      - reward is expectancy-normalised PnL: clip(pnl / risk, -1, 1),
        NOT binary +1/-1 (a $1 win and a $100 win are not the same lesson).
      - next_state is the REAL state at exit, not the current state
        (original set next_state = state, which breaks the Bellman update).
      - state is the 5-bar return bucket (strong_bull/bull/neutral/bear/
        strong_bear), as in the original.
    Training: learns during the train split; in the test split epsilon is
    pinned low and learning is frozen (alpha=0) for an honest read.
    """
    name = "Q_LEARNING"
    STATES = ["strong_bull", "bull", "neutral", "bear", "strong_bear"]
    ACTIONS = ["BUY", "SELL", "HOLD"]

    def __init__(self, epsilon: float = 0.10) -> None:
        super().__init__()
        self.q: dict[str, dict[str, float]] = {s: {a: 0.0 for a in self.ACTIONS} for s in self.STATES}
        self.alpha = 0.1
        self.gamma = 0.9
        self.epsilon = epsilon
        self.frozen = False  # set True in the test split
        self._pending: dict | None = None  # (state, action, risk) awaiting exit

    @staticmethod
    def state_of(df: pd.DataFrame) -> str:
        if len(df) < 6:
            return "neutral"
        ret = df["close"].iloc[-1] / df["close"].iloc[-6] - 1.0
        if ret > 0.05:
            return "strong_bull"
        if ret > 0.02:
            return "bull"
        if ret < -0.05:
            return "strong_bear"
        if ret < -0.02:
            return "bear"
        return "neutral"

    def tick(self, symbol: str, df: pd.DataFrame, breadth: float = 0.0) -> Signal | None:
        if len(df) < 6:
            return None
        state = self.state_of(df)
        if random.random() < self.epsilon and not self.frozen:
            action = random.choice(self.ACTIONS)
        else:
            action = max(self.q[state], key=lambda a: self.q[state][a])
        price = float(df["close"].iloc[-1])
        if action == "BUY":
            self._pending = {"state": state, "action": action, "risk": price * 0.015}
            return Signal(self.name, symbol, "long", price,
                          price * 1.03, price * 0.985, 0.60)
        if action == "SELL":
            self._pending = {"state": state, "action": action, "risk": price * 0.015}
            return Signal(self.name, symbol, "short", price,
                          price * 0.97, price * 1.015, 0.60)
        return None

    def learn(self, pnl: float, exit_df: pd.DataFrame) -> None:
        """Call on exit with the REAL exit-state. No-op when frozen."""
        if self.frozen or not self._pending:
            self._pending = None
            return
        p = self._pending
        reward = max(-1.0, min(1.0, pnl / max(p["risk"], 1e-9)))
        next_state = self.state_of(exit_df)
        old = self.q[p["state"]][p["action"]]
        best_next = max(self.q[next_state].values())
        self.q[p["state"]][p["action"]] = old + self.alpha * (
            reward + self.gamma * best_next - old)
        self._pending = None
        self.epsilon = max(0.01, self.epsilon * 0.999)


# ------------------------------------------------------------- Echo (FFT + shape)
class EchoAgent(Agent):
    """Gravia Echo Frequency (EFP) — signal producer, not an executor.
    Two techniques fused, as in the design doc:
      (a) FFT spectral analysis on detrended log-closes (last 64 bars):
          find the dominant cycle (period 8-32 bars) and its current slope.
      (b) Normalised sliding-window shape matching: has this exact 16-bar
          price shape happened before, and what did price do in the 4 bars
          after it? Needs correlation > 0.85 and a >1% follow-through.
    Both must agree in direction. TP 2%, SL 1%. Rare by design — it is a
    producer whose signals other agents could consume via the INTEL_BUS.
    """
    name = "ECHO"

    def tick(self, symbol: str, df: pd.DataFrame, breadth: float = 0.0) -> Signal | None:
        import numpy as np
        if len(df) < 600:
            return None
        close = df["close"].to_numpy(dtype=float)
        price = float(close[-1])
        # (a) FFT dominant cycle
        window = np.log(close[-64:])
        x = np.arange(64)
        trend = np.polyfit(x, window, 1)
        detrended = window - np.polyval(trend, x)
        spec = np.abs(np.fft.rfft(detrended))
        spec[0] = 0.0
        k = int(np.argmax(spec))
        if k == 0:
            return None
        period = 64.0 / k
        if not (8.0 <= period <= 32.0):
            return None
        # slope of the dominant sinusoid at the last point
        phase = np.angle(np.fft.rfft(detrended)[k])
        slope = -math.sin(2 * math.pi * k * 63 / 64 + phase)
        fft_dir = 1 if slope > 0.3 else (-1 if slope < -0.3 else 0)
        if fft_dir == 0:
            return None
        # (b) shape matching on 16-bar log-return shapes — bounded search:
        # last 1,000 bars only, step 8 (keeps the 1h backtest tractable).
        rets = np.diff(np.log(close))
        shape = rets[-16:]
        shape = (shape - shape.mean()) / (shape.std() or 1.0)
        best_corr, best_next = -1.0, 0.0
        search_from = max(0, len(rets) - 1000)
        for start in range(search_from, len(rets) - 16 - 4, 8):
            past = rets[start:start + 16]
            past = (past - past.mean()) / (past.std() or 1.0)
            corr = float(np.corrcoef(shape, past)[0, 1])
            if corr > best_corr:
                best_corr = corr
                best_next = float(np.sum(rets[start + 16:start + 20]))
        if best_corr < 0.85 or abs(best_next) < 0.01:
            return None
        shape_dir = 1 if best_next > 0 else -1
        if shape_dir != fft_dir:
            return None
        direction = "long" if fft_dir > 0 else "short"
        conf = min(0.85, 0.60 + (best_corr - 0.85) * 2)
        if direction == "long":
            return Signal(self.name, symbol, "long", price,
                          price * 1.02, price * 0.99, conf)
        return Signal(self.name, symbol, "short", price,
                      price * 0.98, price * 1.01, conf)


ALL_AGENTS = [FomoPanicAgent, RsiMeanReversionAgent, BollingerFadeAgent,
              BreakoutAgent, QLearningAgent, EchoAgent]

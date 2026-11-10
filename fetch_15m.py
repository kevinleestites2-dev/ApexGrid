"""Fetch 15m klines from Binance.US (public, no key) for the 15-minute
Dump & Hedge family of strategies. Same range as the 1h/4h sets."""
import json, os, time, urllib.request

BASE = "https://api.binance.us/api/v3/klines"
START = int(time.mktime(time.strptime("2024-01-01", "%Y-%m-%d")) * 1000)
END = int(time.time() * 1000)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

def fetch(symbol):
    bars, start = [], START
    while True:
        url = f"{BASE}?symbol={symbol}&interval=15m&startTime={start}&limit=1000"
        with urllib.request.urlopen(url, timeout=30) as r:
            chunk = json.load(r)
        if not chunk:
            break
        bars.extend(chunk)
        start = chunk[-1][0] + 1
        if chunk[-1][0] >= END or len(chunk) < 1000:
            break
    out = [{"t": b[0], "open": float(b[1]), "high": float(b[2]), "low": float(b[3]),
            "close": float(b[4]), "volume": float(b[5])} for b in bars]
    path = os.path.join(OUT, f"{symbol}_15m.json")
    json.dump(out, open(path, "w"))
    print(symbol, len(out), "bars", out[0]["t"], "->", out[-1]["t"], "saved", path)

if __name__ == "__main__":
    for s in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        fetch(s)

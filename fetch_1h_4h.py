"""fetch_1h_4h.py — Fetch 1h / 4h (/ 1d) klines from Binance.US.

Public endpoint, no key — same pattern as fetch_15m.py, so a fresh
clone can rebuild data/*_1h.json and *_4h.json (and *_1d.json for the
v3 daily tests, which are otherwise resampled from 1h in
experiments_v3.py).

Usage:
    python3 fetch_1h_4h.py            # all symbols, 1h + 4h, 2024-01-01 -> now
    python3 fetch_1h_4h.py 1d         # also fetch daily bars
    python3 fetch_1h_4h.py --help

The fetch() function also accepts start_ms/end_ms so tests can probe
a tiny window without re-downloading ~2.9 years (see smoke_v3.py).
Paper / simulation ONLY. LIVE_MODE=False everywhere. No keys.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

BASE = "https://api.binance.us/api/v3/klines"
START = int(time.mktime(time.strptime("2024-01-01", "%Y-%m-%d")) * 1000)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def fetch(symbol, interval, start_ms=None, end_ms=None, out_dir=None):
    """Fetch klines for one symbol/interval. Returns the bar list and
    writes data/{symbol}_{interval}.json (dict rows, same shape as the
    existing data files). Pass out_dir to write elsewhere (tests use a
    temp dir so a probe never overwrites the real data files)."""
    start = START if start_ms is None else int(start_ms)
    end = int(time.time() * 1000) if end_ms is None else int(end_ms)
    bars = []
    cur = start
    while True:
        url = (f"{BASE}?symbol={symbol}&interval={interval}"
               f"&startTime={cur}&limit=1000")
        with urllib.request.urlopen(url, timeout=30) as r:
            chunk = json.load(r)
        if not chunk:
            break
        bars.extend(chunk)
        cur = chunk[-1][0] + 1
        if chunk[-1][0] >= end or len(chunk) < 1000:
            break
    out = [{"t": b[0], "open": float(b[1]), "high": float(b[2]),
            "low": float(b[3]), "close": float(b[4]),
            "volume": float(b[5])} for b in bars]
    os.makedirs(OUT if out_dir is None else out_dir, exist_ok=True)
    path = os.path.join(OUT if out_dir is None else out_dir, f"{symbol}_{interval}.json")
    json.dump(out, open(path, "w"))
    print(symbol, interval, len(out), "bars",
          out[0]["t"] if out else None, "->",
          out[-1]["t"] if out else None, "saved", path)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("intervals", nargs="*", default=["1h", "4h"],
                    help="intervals to fetch (default: 1h 4h; add 1d for daily)")
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    args = ap.parse_args()
    for iv in args.intervals:
        if iv not in ("1h", "4h", "1d", "15m"):
            print(f"unsupported interval {iv!r}; use 1h, 4h, 1d (or 15m)")
            sys.exit(2)
        for s in args.symbols:
            fetch(s, iv)


if __name__ == "__main__":
    main()

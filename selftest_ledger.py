"""Self-test for honest_ledger.py — known-answer checks. Run: python3 selftest_ledger.py"""
import sys
sys.path.insert(0, "/home/hatch/workspace/goals/swarm-training-trading-bot/hidden_files")
from honest_ledger import Ledger, Trade, score, scoreboard, allocate, trade_pnl


def mk(strategy, entry, exit_, side="long", qty=1.0, fee=0.0, slip=0.0):
    return Trade(strategy=strategy, venue="test", symbol="SOL-PERP", side=side,
                 entry_price=entry, exit_price=exit_, qty=qty,
                 fee_entry=fee, fee_exit=fee, slippage_bps=slip)


# 1. Known-answer expectancy: 6 wins of +$10, 4 losses of -$5, no fees.
#    expectancy = 0.6*10 - 0.4*5 = 4.0
trades = [mk("A", 100, 110) for _ in range(6)] + [mk("A", 100, 95) for _ in range(4)]
s = score(trades)
assert abs(s["expectancy"] - 4.0) < 1e-9, s
assert abs(s["win_rate"] - 0.6) < 1e-9, s
assert abs(s["profit_factor"] - (60.0 / 20.0)) < 1e-9, s
assert s["sample_ok"] == 0.0 and s["n"] == 10.0  # below MIN_SAMPLE -> unproven
print("1. expectancy math OK:", s["expectancy"])

# 2. Fees and slippage always subtract: $10 gross win, $1 fees, 10bps on $100 notional = $0.10
t = mk("A", 100, 110, fee=0.5, slip=10.0)
pnl = trade_pnl(t)
assert abs(pnl - (10.0 - 1.0 - 0.10)) < 1e-9, pnl
print("2. fees+slippage OK:", pnl)

# 3. Fake fills are rejected, not scored.
for bad in [dict(exit_=0), dict(exit_=-5), dict(exit_=float("nan"))]:
    try:
        trade_pnl(mk("A", 100, bad["exit_"]))
        raise AssertionError(f"accepted dishonest fill {bad}")
    except ValueError:
        pass
try:
    trade_pnl(mk("A", 100, 110, side="sideways"))
    raise AssertionError("accepted bad side")
except ValueError:
    pass
print("3. fake-fill rejection OK")

# 4. Scoreboard sorts by expectancy; allocator funds only proven winners.
led = Ledger()
for _ in range(40):  # proven winner: 70% x +$8 vs 30% x -$4 -> exp = 4.4
    led.record(mk("winner", 100, 108 if _ % 10 < 7 else 96))
for _ in range(40):  # proven loser: 40% x +$5 vs 60% x -$6 -> exp = -1.6
    led.record(mk("loser", 100, 105 if _ % 10 < 4 else 94))
for _ in range(5):   # unproven hot streak -> must stay benched
    led.record(mk("rookie", 100, 120))
board = scoreboard(led)
# rookie sorts first on raw expectancy (20.0 > 4.4) — but stays benched:
# high expectancy with n=5 is noise, and the allocator knows it.
assert [r["strategy"] for r in board] == ["rookie", "winner", "loser"], board
alloc = allocate(board, 10000.0)
assert alloc["winner"] == 10000.0, alloc
assert alloc["loser"] == 0.0 and alloc["rookie"] == 0.0, alloc
print("4. scoreboard+allocator OK (hot rookie benched despite top expectancy):",
      {k: round(v) for k, v in alloc.items()})

# 5. Max drawdown: +10, +10, -25, +10 -> peak 20, trough -5, DD = 25
dd_trades = [mk("D", 100, 110), mk("D", 100, 110), mk("D", 100, 75), mk("D", 100, 110)]
s5 = score(dd_trades)
assert abs(s5["max_drawdown"] - 25.0) < 1e-9, s5
print("5. max drawdown OK:", s5["max_drawdown"])

# 6. One strategy's garbage can't poison another's score.
led2 = Ledger()
led2.record(mk("good", 100, 110))
try:
    led2.record(mk("bad", 100, 0))  # rejected at record() time
    raise AssertionError("bad fill recorded")
except ValueError:
    pass
assert len(led2.trades()) == 1 and led2.trades()[0].strategy == "good"
print("6. fault isolation OK")

print("\nAll honest_ledger self-tests passed.")

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.player import get_career_stats

fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got}" + ("" if ok else f"   (expected {want})"))


def stats(name):
    r = get_career_stats(name)
    assert r["ok"], r
    return r["data"]


k = stats("V Kohli")["batting"]
check("Kohli innings", k["innings"], 259)
check("Kohli runs", k["runs"], 8661)
check("Kohli outs", k["outs"], 219)
check("Kohli high score", k["high_score"], 113)
check("Kohli fifties", k["fifties"], 63)
check("Kohli hundreds", k["hundreds"], 8)

d = stats("MS Dhoni")["batting"]
check("Dhoni innings/runs", (d["innings"], d["runs"]), (241, 5439))
r = stats("RG Sharma")["batting"]
check("Rohit innings/runs", (r["innings"], r["runs"]), (267, 7046))

for name, wk, inn in [("DJ Bravo", 183, 158), ("SL Malinga", 170, 122),
                      ("YS Chahal", 221, 172), ("JJ Bumrah", 183, 145),
                      ("Navdeep Saini", 23, 32)]:
    b = stats(name)["bowling"]
    check(f"{name} wickets/innings", (b["wickets"], b["innings"]), (wk, inn))

amb = get_career_stats("sharma")
check("'sharma' is ambiguous", (amb["ok"], len(amb["candidates"]) > 1), (False, True))
check("typed name works", get_career_stats("virat kohli")["data"]["player"], "V Kohli")

print("\nfailures:", fails)

print("\n--- compare with what you know ---")
for n in ["V Kohli", "JJ Bumrah", "DJ Bravo", "SL Malinga", "Rashid Khan", "RG Sharma"]:
    s = stats(n)
    b = s.get("bowling", {})
    print(f"{n:14} role={s['role']:12} best bowling={b.get('best_figures', '-')}")
print("\nKohli batting record:")
print(stats("V Kohli")["batting"])
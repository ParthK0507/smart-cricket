import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.player import get_career_stats, get_season_stats, get_phase_stats

fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got}" + ("" if ok else f"   (expected {want})"))


ss = get_season_stats("V Kohli")["data"]["batting"]
r16 = next(r for r in ss if r["year"] == 2016)
check("Kohli 2016 runs/hundreds", (r16["runs"], r16["hundreds"]), (973, 4))
check("Kohli seasons", len(ss), 18)

ph = get_phase_stats("V Kohli")["data"]["batting"]
check("Kohli phase runs/balls/outs",
      tuple(sum(ph[p][k] for p in ph) for k in ("runs", "balls", "outs")), (8661, 6519, 219))
check("Kohli death SR > middle SR", ph["death"]["sr"] > ph["middle"]["sr"], True)
ph16 = get_phase_stats("V Kohli", 2016)["data"]["batting"]
check("Kohli 2016 phase runs", sum(ph16[p]["runs"] for p in ph16), 973)

bw = get_phase_stats("JJ Bumrah")["data"]["bowling"]
career = get_career_stats("JJ Bumrah")["data"]["bowling"]
check("Bumrah phase wickets", sum(bw[p]["wickets"] for p in bw), 183)
check("Bumrah phase balls = career balls", sum(bw[p]["balls"] for p in bw), career["balls"])

for name, role in [("V Kohli", "batter"), ("RG Sharma", "batter"), ("MS Dhoni", "batter"),
                   ("JJ Bumrah", "bowler"), ("SL Malinga", "bowler"), ("DJ Bravo", "all-rounder"),
                   ("RA Jadeja", "all-rounder"), ("SP Narine", "all-rounder")]:
    check(f"role {name}", get_career_stats(name)["data"]["role"], role)

print("\nfailures:", fails)

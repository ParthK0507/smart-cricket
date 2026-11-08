import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.opposition import get_opposition_stats
from core.teams import _canonical_teams

fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got}" + ("" if ok else f"   (expected {want})"))


b = get_opposition_stats("kohli", "csk")["data"]["batting"]
check("Kohli v CSK innings/runs/balls/outs", (b["innings"], b["runs"], b["balls"], b["outs"]), (34, 1146, 897, 30))
check("  year totals add up", tuple(sum(y[k] for y in b["by_year"]) for k in ("innings", "runs", "balls", "outs")), (34, 1146, 897, 30))
check("  phase totals add up", tuple(sum(p[k] for p in b["by_phase"].values()) for k in ("runs", "balls", "outs")), (1146, 897, 30))
check("  CSK did not play in 2016/2017", {y["year"] for y in b["by_year"]} & {2016, 2017}, set())

w = get_opposition_stats("bumrah", "chennai")["data"]["bowling"]
check("Bumrah v CSK innings/balls/wickets", (w["innings"], w["balls"], w["wickets"]), (16, 370, 14))


def across_all_teams(name, role, keys):
    tot = dict.fromkeys(keys, 0)
    for t in _canonical_teams():
        r = get_opposition_stats(name, t)
        if r["ok"] and role in r["data"]:
            for k in keys:
                tot[k] += r["data"][role][k]
    return tuple(tot[k] for k in keys)


check("Kohli across all teams = career", across_all_teams("V Kohli", "batting", ("innings", "runs", "balls", "outs")), (259, 8661, 6519, 219))
check("Bumrah across all teams = career", across_all_teams("JJ Bumrah", "bowling", ("innings", "wickets")), (145, 183))

check("ambiguous team fails", get_opposition_stats("kohli", "gujarat")["ok"], False)
check("unknown player fails", get_opposition_stats("xyzzy", "csk")["ok"], False)
check("unknown team fails", get_opposition_stats("kohli", "xyzzy")["ok"], False)

print("\nfailures:", fails)

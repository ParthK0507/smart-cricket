import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.venue_stats import get_venue_stats
from core.venues import _canonical_venues

fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got}" + ("" if ok else f"   (expected {want})"))


b = get_venue_stats("kohli", "chinnaswamy")["data"]["batting"]
check("Kohli at Chinnaswamy innings/runs/balls/outs", (b["innings"], b["runs"], b["balls"], b["outs"]), (91, 3202, 2230, 80))
check("  year totals add up", tuple(sum(y[k] for y in b["by_year"]) for k in ("innings", "runs", "balls", "outs")), (91, 3202, 2230, 80))
check("  phase totals add up", tuple(sum(p[k] for p in b["by_phase"].values()) for k in ("runs", "balls", "outs")), (3202, 2230, 80))
check("  no matches in 2009/2020/2021/2022", {y["year"] for y in b["by_year"]} & {2009, 2020, 2021, 2022}, set())

for v, inns, runs in [("wankhede", 86, 2451), ("chepauk", 16, 364)]:
    r = get_venue_stats("rohit sharma", v)["data"]["batting"]
    check(f"Rohit at {v} innings/runs", (r["innings"], r["runs"]), (inns, runs))

w = get_venue_stats("bumrah", "wankhede")["data"]["bowling"]
check("Bumrah at Wankhede innings/balls/wickets", (w["innings"], w["balls"], w["wickets"]), (48, 1129, 64))


def across_all_grounds(name, role, keys):
    tot = dict.fromkeys(keys, 0)
    for v in _canonical_venues():
        r = get_venue_stats(name, v)
        if r["ok"] and role in r["data"]:
            for k in keys:
                tot[k] += r["data"][role][k]
    return tuple(tot[k] for k in keys)


check("Kohli across all grounds = career", across_all_grounds("V Kohli", "batting", ("innings", "runs", "balls", "outs")), (259, 8661, 6519, 219))
check("Bumrah across all grounds = career", across_all_grounds("JJ Bumrah", "bowling", ("innings", "wickets")), (145, 183))

check("ambiguous ground fails", get_venue_stats("kohli", "mumbai")["ok"], False)
check("unknown player fails", get_venue_stats("xyzzy", "wankhede")["ok"], False)
check("unknown ground fails", get_venue_stats("kohli", "xyzzy")["ok"], False)
check("no record at ground fails", get_venue_stats("kohli", "vizag")["ok"], False)

print("\nfailures:", fails)

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.matchup import get_bowler_matchup

fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got}" + ("" if ok else f"   (expected {want})"))


for b, o, runs, balls, outs in [("kohli", "ashwin", 181, 149, 1), ("warner", "narine", 195, 123, 2),
                                ("rohit sharma", "umesh yadav", 170, 118, 5)]:
    d = get_bowler_matchup(b, o)["data"]
    check(f"{b} v {o}", (d["runs"], d["balls"], d["dismissals"]), (runs, balls, outs))
    check("  year totals add up", tuple(sum(y[k] for y in d["by_year"]) for k in ("runs", "balls", "outs")), (runs, balls, outs))
    check("  phase totals add up", tuple(sum(p[k] for p in d["by_phase"]) for k in ("runs", "balls", "outs")), (runs, balls, outs))

r = get_bowler_matchup("kohli", "ashwin")
check("chart lengths match", len(r["chart"]["x"]) == len(r["chart"]["runs"]) == len(r["chart"]["sr"]), True)
check("ambiguous batter fails", get_bowler_matchup("sharma", "bumrah")["ok"], False)
check("unknown bowler fails", get_bowler_matchup("kohli", "xyzzy")["ok"], False)
check("never faced fails", get_bowler_matchup("SR Tendulkar", "Rashid Khan")["ok"], False)

print("\nfailures:", fails)

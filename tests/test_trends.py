import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.data import table
from core.trends import get_career_trends, _league_sr, _league_econ

fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got}" + ("" if ok else f"   (expected {want})"))


bat_all, bowl_all = table("player_match_batting"), table("player_match_bowling")

# ---- batters: results must equal an independent calculation on the match table
for name in ["V Kohli", "MS Dhoni", "RG Sharma", "AB de Villiers", "KL Rahul"]:
    r = get_career_trends(name)["data"]["batting"]
    runs = bat_all[bat_all["batter"] == name].sort_values("inning_no")["runs"].tolist()
    roll = pd.Series(runs).rolling(10).sum().dropna()
    check(f"{name}: season runs/innings add up",
          (sum(s["runs"] for s in r["seasons"]), sum(s["innings"] for s in r["seasons"])), (sum(runs), len(runs)))
    check("  best/worst 10-innings window", (r["best_window"]["runs"], r["worst_window"]["runs"]),
          (int(roll.max()), int(roll.min())))
    check("  recent form", r["recent_form"]["runs"], sum(runs[-10:]))

k = get_career_trends("V Kohli")
kb = k["data"]["batting"]
check("Kohli best season", kb["events"]["best_season"]["year"], 2016)
check("Kohli best 10 innings", (kb["best_window"]["runs"], kb["best_window"]["from"], kb["best_window"]["to"]),
      (678, "2016-04-22", "2016-05-18"))
check("Kohli worst 10 innings", kb["worst_window"]["runs"], 129)
check("Kohli team spans", [t["team"] for t in kb["teams"]], ["Royal Challengers Bengaluru"])
ch = k["chart"]["batting"]["rolling"]
check("Kohli chart lengths", (len(ch["x"]), len(ch["roll_avg"]), len(ch["roll_sr"]), len(ch["date"])), (259, 259, 259, 259))
check("Kohli verdict is league-adjusted", (kb["trend"]["direction"], kb["trend"]["direction_raw"]), ("steady", "improved"))
check("Dhoni best/worst 10 innings", (get_career_trends("MS Dhoni")["data"]["batting"]["best_window"]["runs"],
                                      get_career_trends("MS Dhoni")["data"]["batting"]["worst_window"]["runs"]), (405, 78))
check("Rohit best/worst 10 innings", (get_career_trends("RG Sharma")["data"]["batting"]["best_window"]["runs"],
                                      get_career_trends("RG Sharma")["data"]["batting"]["worst_window"]["runs"]), (433, 135))
check("Dhoni has no bowling block", "bowling" in get_career_trends("MS Dhoni")["data"], False)

# ---- bowlers
for name in ["JJ Bumrah", "SL Malinga", "YS Chahal", "R Ashwin"]:
    r = get_career_trends(name)["data"]["bowling"]
    w = bowl_all[bowl_all["bowler"] == name].sort_values("inning_no")["wickets"].tolist()
    roll = pd.Series(w).rolling(10).sum().dropna()
    check(f"{name}: season wickets add up", sum(s["wickets"] for s in r["seasons"]), sum(w))
    check("  best/worst 10-innings window", (r["best_window"]["wickets"], r["worst_window"]["wickets"]),
          (int(roll.max()), int(roll.min())))
    check("  recent form", r["recent_form"]["wickets"], sum(w[-10:]))

bb = get_career_trends("JJ Bumrah")["data"]["bowling"]
check("Bumrah best 10 innings", (bb["best_window"]["wickets"], bb["best_window"]["from"], bb["best_window"]["to"]),
      (22, "2020-10-04", "2020-11-05"))
check("Malinga best 10 innings", get_career_trends("SL Malinga")["data"]["bowling"]["best_window"]["wickets"], 24)
check("Chahal best 10 innings", get_career_trends("YS Chahal")["data"]["bowling"]["best_window"]["wickets"], 24)

# ---- league baselines
check("league SR 2008 / 2025", (round(_league_sr([2008]), 1), round(_league_sr([2025]), 1)), (129.0, 152.5))
check("league economy 2009 / 2025", (round(_league_econ([2009]), 1), round(_league_econ([2025]), 1)), (7.3, 9.5))

# ---- errors
check("ambiguous name fails", get_career_trends("sharma")["ok"], False)
check("unknown name fails", get_career_trends("xyzzy")["ok"], False)

print("\nfailures:", fails)

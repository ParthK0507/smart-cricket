import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.compare import compare_players
from core.data import table
from core.player import get_career_stats, get_phase_stats

fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got}" + ("" if ok else f"   (expected {want})"))


# 1) scorecard values equal the individually tested functions
r = compare_players(["V Kohli", "SK Raina"])["data"]
for n in ["V Kohli", "SK Raina"]:
    c = get_career_stats(n)["data"]["batting"]
    ph = get_phase_stats(n)["data"]["batting"]
    check(f"{n}: avg/sr match career stats", (r["metrics"]["avg"]["values"][n], r["metrics"]["sr"]["values"][n]), (c["avg"], c["sr"]))
    check(f"{n}: death SR matches phase stats", r["metrics"]["death_sr"]["values"][n], ph["death"]["sr"])
check("Kohli runs in context", r["context"]["runs"]["V Kohli"], 8661)

# 2) typed names work, and the order of players changes nothing
check("typed names", compare_players(["kohli", "SK Raina"])["ok"], True)
a = compare_players(["V Kohli", "SK Raina"])["data"]
b = compare_players(["SK Raina", "V Kohli"])["data"]
check("order does not change wins/ties", (a["wins"], a["ties"]), (b["wins"], b["ties"]))
check("order does not change winners", {k: m["winner"] for k, m in a["metrics"].items()},
      {k: m["winner"] for k, m in b["metrics"].items()})

# 3) wins + ties = number of scored metrics (10)
for names in [["V Kohli", "SK Raina"], ["V Kohli", "RG Sharma", "MS Dhoni"], ["JJ Bumrah", "SL Malinga", "YS Chahal"]]:
    d = compare_players(names)["data"]
    check(f"wins+ties = 10 for {names}", (sum(d["wins"].values()) + d["ties"], d["scored_metrics"]), (10, 10))

# 4) era adjustment recomputed with a separate loop
s = table("player_season_batting")
lg = s.groupby("year")[["runs", "balls", "outs"]].sum()
num = den = 0.0
for _, row in s[s["batter"] == "V Kohli"].iterrows():
    L = lg.loc[row["year"]]
    num += row["balls"] * (L["runs"] / L["balls"] * 100)
    den += row["balls"]
expected = get_career_stats("V Kohli")["data"]["batting"]["sr"] - num / den
got = a["metrics"]["sr_vs_league"]["values"]["V Kohli"]
check("Kohli SR vs league recomputed", abs(got - expected) < 0.01, True)

# 5) radar: the best player scores exactly 1.0 on every axis
rad = compare_players(["V Kohli", "RG Sharma", "MS Dhoni"])["chart"]["radar"]
check("radar best = 1.0 on every axis",
      all(max(rad["series"][n][i] for n in rad["series"]) == 1.0 for i in range(len(rad["axes"]))), True)

# 6) bowling comparison and all-rounders
bw = compare_players(["JJ Bumrah", "SL Malinga", "YS Chahal"])["data"]
check("bowling role", bw["role"], "bowling")
check("bowling wickets in context", bw["context"]["wickets"], {"JJ Bumrah": 183, "SL Malinga": 170, "YS Chahal": 221})
check("all-rounders with role=bowling", compare_players(["DJ Bravo", "RA Jadeja"], role="bowling")["ok"], True)

# 7) errors
check("mixed roles fail", compare_players(["V Kohli", "JJ Bumrah"])["ok"], False)
check("one player fails", compare_players(["kohli"])["ok"], False)
check("ambiguous name fails", compare_players(["kohli", "sharma"])["ok"], False)
check("same player twice fails", compare_players(["kohli", "virat kohli"])["ok"], False)

print("\nfailures:", fails)

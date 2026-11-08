import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.data import table
from core.home_away import get_home_away_stats, venue_context

fails = 0


def check(label, got, want=True):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got}" + ("" if ok else f"   (expected {want})"))


CASES = [
    (("Chennai Super Kings", "Mumbai Indians", 2019, "MA Chidambaram Stadium, Chennai"), "home"),
    (("Mumbai Indians", "Chennai Super Kings", 2019, "MA Chidambaram Stadium, Chennai"), "away"),
    (("Chennai Super Kings", "Kolkata Knight Riders", 2018, "MA Chidambaram Stadium, Chennai"), "home"),
    (("Rajasthan Royals", "Punjab Kings", 2024, "Barsapara Cricket Stadium, Guwahati"), "home"),
    (("Royal Challengers Bengaluru", "Sunrisers Hyderabad", 2016, "M Chinnaswamy Stadium, Bengaluru"), "home"),
    (("Sunrisers Hyderabad", "Royal Challengers Bengaluru", 2016, "M Chinnaswamy Stadium, Bengaluru"), "away"),
    (("Mumbai Indians", "Delhi Capitals", 2020, "Dubai International Cricket Stadium, Dubai"), "neutral"),
    (("Mumbai Indians", "Chennai Super Kings", 2009, "Kingsmead, Durban"), "neutral"),
    (("Mumbai Indians", "Chennai Super Kings", 2022, "Wankhede Stadium, Mumbai"), "neutral"),
    (("Kolkata Knight Riders", "Delhi Capitals", 2014, "Sharjah Cricket Stadium, Sharjah"), "neutral"),
    (("Kolkata Knight Riders", "Delhi Capitals", 2014, "Eden Gardens, Kolkata"), "home"),
    (("Kolkata Knight Riders", "Rajasthan Royals", 2025, "Arun Jaitley Stadium, Delhi"), "neutral"),
    (("Delhi Capitals", "Kolkata Knight Riders", 2025, "Arun Jaitley Stadium, Delhi"), "home"),
]
for args, want in CASES:
    check(f"{args[0]} v {args[1]} {args[2]} at {args[3].split(',')[0]}", venue_context(*args), want)

# ---- totals: home + away + neutral = career
h = get_home_away_stats("V Kohli")["data"]["batting"]
check("Kohli home+away+neutral = career",
      tuple(sum(h[s][k] for s in h) for k in ("innings", "runs", "balls", "outs")), (259, 8661, 6519, 219))
check("Kohli home = his Chinnaswamy games", (h["home"]["innings"], h["home"]["runs"]), (91, 3202))
s = table("player_season_batting")
neutral_floor = int(s[(s["batter"] == "V Kohli") & s["year"].isin([2009, 2020, 2021, 2022])]["innings"].sum())
check("Kohli neutral covers at least the neutral seasons", h["neutral"]["innings"] >= neutral_floor)

for name in ["MS Dhoni", "RG Sharma"]:
    b = get_home_away_stats(name)["data"]["batting"]
    c = table("career_batting").set_index("batter").loc[name]
    check(f"{name} home+away+neutral = career",
          tuple(sum(b[x][k] for x in b) for k in ("innings", "runs", "outs")),
          (int(c["innings"]), int(c["runs"]), int(c["outs"])))

w = get_home_away_stats("JJ Bumrah")["data"]["bowling"]
check("Bumrah home+away+neutral = career", tuple(sum(w[x][k] for x in w) for k in ("innings", "wickets")), (145, 183))
check("Bumrah has no batting split worth showing", "bowling" in get_home_away_stats("JJ Bumrah")["data"], True)

# ---- errors
check("ambiguous name fails", get_home_away_stats("sharma")["ok"], False)
check("unknown name fails", get_home_away_stats("xyzzy")["ok"], False)

print("\nfailures:", fails)

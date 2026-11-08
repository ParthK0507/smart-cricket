import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.data import table
from core.leaderboard import get_leaderboard

fails = 0


def check(label, got, want=True):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got}" + ("" if ok else f"   (expected {want})"))


def rows(*a, **k):
    return get_leaderboard(*a, **k)["data"]["rows"]


# ---- batting: all-time rows equal the career table exactly
cb = table("career_batting").set_index("batter")
top = rows("runs", top=10)
check("top-10 runs rows equal career_batting",
      all((r["runs"], r["innings"], r["outs"]) == (int(cb.loc[r["player"]]["runs"]), int(cb.loc[r["player"]]["innings"]),
                                                    int(cb.loc[r["player"]]["outs"])) for r in top))
check("top-10 averages and consistency equal career_batting",
      all(abs(r["avg"] - cb.loc[r["player"]]["avg"]) < 1e-3 and abs(r["consistency"] - cb.loc[r["player"]]["consistency"]) < 1e-3
          for r in top))
check("sorted high to low", [r["value"] for r in top] == sorted((r["value"] for r in top), reverse=True))
check("leader of all-time runs", (top[0]["player"], top[0]["value"]), ("V Kohli", 8661))

# ---- batting: filtered totals equal the underlying tables
bat = table("player_match_batting")
seasons = table("player_season_batting")
for y in (2016, 2024):
    got = sum(r["runs"] for r in rows("runs", top=1000, year=y))
    check(f"all runs in {y} = season table", got, int(seasons[seasons["year"] == y]["runs"].sum()))
check("CSK runs in 2018", sum(r["runs"] for r in rows("runs", top=1000, year=2018, team="csk")),
      int(bat[(bat["year"] == 2018) & (bat["batting_team"] == "Chennai Super Kings")]["runs"].sum()))
check("runs at Wankhede", sum(r["runs"] for r in rows("runs", top=1000, venue="wankhede")),
      int(bat[bat["venue"] == "Wankhede Stadium, Mumbai"]["runs"].sum()))
check("2016 top run-scorer", (rows("runs", top=1, year=2016)[0]["player"], rows("runs", top=1, year=2016)[0]["value"]), ("V Kohli", 973))
check("2024 top run-scorer runs", rows("runs", top=1, year=2024)[0]["value"], 741)

# ---- bowling
cw = table("career_bowling").set_index("bowler")
bt = rows("wickets", role="bowling", top=10)
check("leader of all-time wickets", (bt[0]["player"], bt[0]["value"]), ("YS Chahal", 221))
check("top-10 wicket rows equal career_bowling",
      all((r["wickets"], r["innings"], r["balls"]) == (int(cw.loc[r["player"]]["wickets"]), int(cw.loc[r["player"]]["innings"]),
                                                       int(cw.loc[r["player"]]["balls"])) for r in bt))
check("all wickets in 2022 = season table",
      sum(r["wickets"] for r in rows("wickets", role="bowling", top=1000, year=2022)),
      int(table("player_season_bowling").query("year == 2022")["wickets"].sum()))

# ---- rate metrics: qualification and ordering
eco = rows("economy", role="bowling", top=10)
check("economy leaders have 20+ innings", all(r["innings"] >= 20 for r in eco))
check("economy sorted low to high", [r["value"] for r in eco] == sorted(r["value"] for r in eco))
check("economy values equal career_bowling", all(abs(r["economy"] - cw.loc[r["player"]]["economy"]) < 1e-3 for r in eco))
check("min_innings override works", all(r["innings"] >= 100 for r in rows("sr", min_innings=100)))

# ---- errors
check("unknown metric fails", get_leaderboard("nonsense")["ok"], False)
check("bowling metric on batting fails", get_leaderboard("economy", role="batting")["ok"], False)
check("ambiguous team fails", get_leaderboard("runs", team="gujarat")["ok"], False)
check("year with no data fails", get_leaderboard("runs", year=1999)["ok"], False)
check("top=0 fails", get_leaderboard("runs", top=0)["ok"], False)

print("\nfailures:", fails)

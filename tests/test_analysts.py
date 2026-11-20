import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.analysts import AGENTS, run_agent

fails = 0


def check(label, ok):
    global fails
    ok = bool(ok)
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}")


check("eight agents are registered", len(AGENTS) == 8)

k = run_agent("player_analyst", {"player": "kohli"})
check("player analyst: career, seasons and phases", k["ok"] and {"career", "seasons", "phases"} <= set(k["results"]))
check("player analyst: Kohli career runs", k["results"]["career"]["data"]["batting"]["runs"] == 8661)
check("insights are well formed", all(i["kind"] in ("strength", "weakness") and i["area"] and any(c.isdigit() for c in i["text"])
                                      for i in k["insights"]))
b = run_agent("player_analyst", {"player": "bumrah"})
check("Bumrah: death-over bowling is a strength", any(i["kind"] == "strength" and "death" in i["text"] for i in b["insights"]))
y = run_agent("player_analyst", {"player": "kohli", "year": 2016})
check("player analyst with a year", y["ok"] and y["results"]["phases"]["data"]["year"] == 2016)

c = run_agent("player_comparator", {"players": ["kohli", "raina"]})
check("comparator: scorecard plus both season tables",
      c["ok"] and {"scorecard", "seasons: V Kohli", "seasons: SK Raina"} <= set(c["results"]))
check("comparator: ten metrics scored", c["results"]["scorecard"]["data"]["scored_metrics"] == 10)

o = run_agent("opposition_analyst", {"player": "kohli", "team": "csk"})
check("opposition: Kohli v CSK", o["results"]["opposition"]["data"]["batting"]["runs"] == 1146)
a = run_agent("opposition_analyst", {"player": "kohli"})
check("all opponents add up to the career runs", sum(r["runs"] for r in a["results"]["all_opponents"]["data"]["batting"]) == 8661)

m = run_agent("matchup_analyst", {"batter": "kohli", "bowler": "ashwin"})["results"]["matchup"]["data"]
check("matchup: Kohli v Ashwin", (m["runs"], m["balls"], m["dismissals"]) == (181, 149, 1))

check("trend analyst", "batting" in run_agent("trend_analyst", {"player": "kohli"})["results"]["trends"]["data"])

v = run_agent("venue_analyst", {"player": "rohit sharma", "venues": ["wankhede", "chepauk"]})["results"]
check("venue analyst: Rohit at Wankhede and Chepauk",
      (v["venue: wankhede"]["data"]["batting"]["innings"], v["venue: chepauk"]["data"]["batting"]["innings"]) == (86, 16))
check("venue analyst: home and away included", v["home_away"]["ok"])

check("predictor: preview", run_agent("match_predictor", {"mode": "preview", "team1": "csk", "team2": "mi", "venue": "wankhede"})["ok"])
ch = run_agent("match_predictor", {"mode": "chase", "batting_first": "csk", "chasing": "mi", "venue": "wankhede", "first_innings_runs": 175})
check("predictor: chase", ch["ok"] and 0 < ch["results"]["chase"]["data"]["chase_win_prob"] < 1)
lv = run_agent("match_predictor", {"mode": "live", "batting_first": "csk", "chasing": "mi", "venue": "wankhede",
                                   "first_innings_runs": 180, "runs": 85, "wickets": 1, "balls_bowled": 60})
check("predictor: live", lv["ok"] and lv["results"]["live"]["data"]["model_used"] == "live")
check("predictor: bad mode fails", not run_agent("match_predictor", {"mode": "nonsense"})["ok"])

lb = run_agent("leaderboard_analyst", {"metric": "runs", "top": 3})["results"]["ranking"]["data"]["rows"]
check("leaderboard: Kohli leads on runs", lb[0]["player"] == "V Kohli" and len(lb) == 3)

amb = run_agent("matchup_analyst", {"batter": "sharma", "bowler": "bumrah"})
check("ambiguous name fails with candidates", (not amb["ok"]) and amb["errors"] and amb["candidates"])
check("unknown agent fails cleanly", not run_agent("nonsense_agent", {})["ok"])
check("wrong arguments fail cleanly", not run_agent("player_analyst", {"wrong_argument": 1})["ok"])

print("\nfailures:", fails)

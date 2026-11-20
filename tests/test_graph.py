import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.graph import ask

fails = 0


def check(label, ok):
    global fails
    ok = bool(ok)
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}")


a = ask({"intents": ["compare"], "players": ["kohli", "raina"]})["answer"]
check("compare: one analyst, scorecard ok", a["agents"] == ["player_comparator"] and a["ok"])
check("compare: ten metrics scored", a["results"][0]["results"]["scorecard"]["data"]["scored_metrics"] == 10)

o = ask({"intents": ["opposition", "compare"], "players": ["kohli", "rohit sharma"], "teams": ["csk"]})["answer"]
check("multi-intent: three analysts, in plan order",
      o["agents"] == ["opposition_analyst", "opposition_analyst", "player_comparator"])
check("multi-intent: Kohli v CSK is right",
      o["results"][0]["results"]["opposition"]["data"]["batting"]["runs"] == 1146)
check("parallel run is deterministic", [r["agent"] for r in ask({"intents": ["opposition", "compare"],
      "players": ["kohli", "rohit sharma"], "teams": ["csk"]})["answer"]["results"]] == o["agents"])

lb = ask({"intents": ["leaderboard"], "metric": "sixes", "year": 2024, "top": 5})["answer"]
rows = lb["results"][0]["results"]["ranking"]["data"]["rows"]
check("leaderboard: five rows, sorted", len(rows) == 5 and [r["value"] for r in rows] == sorted((r["value"] for r in rows), reverse=True))

t = ask({"intents": ["trend", "player_profile"], "players": ["bumrah"]})["answer"]
check("two intents, one player", t["agents"] == ["trend_analyst", "player_analyst"] and t["ok"])

lv = ask({"intents": ["live"], "teams": ["csk", "mi"], "venues": ["wankhede"], "first_innings_runs": 180,
          "runs": 85, "wickets": 1, "balls_bowled": 60})["answer"]
check("live chase through the graph", lv["results"][0]["results"]["live"]["data"]["model_used"] == "live")

amb = ask({"intents": ["matchup"], "players": ["sharma", "bumrah"]})
check("ambiguous name becomes a question, nothing runs", "answer" not in amb and "sharma" in amb["clarify"].lower())
check("unknown player becomes a question", "xyzzy" in ask({"intents": ["player_profile"], "players": ["xyzzy"]})["clarify"])
check("ambiguous team becomes a question", "Gujarat" in ask({"intents": ["opposition"], "players": ["kohli"], "teams": ["gujarat"]})["clarify"])
check("out of scope is declined politely", "IPL" in ask({"intents": ["out_of_scope"]})["clarify"])
check("missing details are requested", "both" in ask({"intents": ["matchup"], "players": ["kohli"]})["clarify"])
check("unknown leaderboard stat is refused", "vibes" in ask({"intents": ["leaderboard"], "metric": "vibes"})["clarify"])
check("live chase without a score is refused", "first-innings score" in ask({"intents": ["live"], "teams": ["csk", "mi"], "venues": ["wankhede"]})["clarify"])

pv = ask({"intents": ["preview"], "teams": ["rcb", "kkr"], "venues": ["eden gardens"], "first_innings_runs": 190})["answer"]
check("a preview with a first-innings score becomes a chase", "chase" in pv["results"][0]["results"])
kv = ask({"intents": ["compare"], "players": ["kohli", "ashwin"]})["answer"]
check("a batter and a bowler compared become a matchup", kv["agents"] == ["matchup_analyst"] and kv["results"][0]["results"]["matchup"]["data"]["runs"] == 181)
bv = ask({"intents": ["compare"], "players": ["bumrah", "kohli"]})["answer"]
check("the order does not matter: the batter stays the batter", bv["results"][0]["results"]["matchup"]["data"]["batter"] == "V Kohli")
print("\nfailures:", fails)

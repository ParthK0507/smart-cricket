import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.critic import _numbers, allowed_numbers, review
from agents.graph import ask

fails = 0


def check(label, ok):
    global fails
    ok = bool(ok)
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}")


def answer(u):
    return ask(u)["answer"]


CASES = {
    "profile": {"intents": ["player_profile"], "players": ["kohli"]},
    "bowler profile": {"intents": ["player_profile"], "players": ["bumrah"]},
    "compare": {"intents": ["compare"], "players": ["kohli", "raina"]},
    "bowling compare": {"intents": ["compare"], "players": ["bumrah", "malinga"]},
    "opposition": {"intents": ["opposition"], "players": ["kohli"], "teams": ["csk"]},
    "all opponents": {"intents": ["opposition"], "players": ["kohli"]},
    "matchup": {"intents": ["matchup"], "players": ["kohli", "ashwin"]},
    "trend": {"intents": ["trend"], "players": ["kohli"]},
    "bowler trend": {"intents": ["trend"], "players": ["bumrah"]},
    "venue": {"intents": ["venue"], "players": ["rohit sharma"], "venues": ["wankhede", "chepauk"]},
    "chase": {"intents": ["chase"], "teams": ["csk", "mi"], "venues": ["wankhede"], "first_innings_runs": 175},
    "live": {"intents": ["live"], "teams": ["csk", "mi"], "venues": ["wankhede"], "first_innings_runs": 180,
             "runs": 85, "wickets": 1, "balls_bowled": 60},
    "preview": {"intents": ["preview"], "teams": ["csk", "mi"], "venues": ["wankhede"]},
    "leaderboard": {"intents": ["leaderboard"], "metric": "runs", "top": 5},
    "bowling leaderboard": {"intents": ["leaderboard"], "metric": "economy", "role": "bowling", "top": 5},
}

# 1) every kind of real answer passes
for label, u in CASES.items():
    r = review(answer(u))
    check(f"clean {label} answer verifies", r["ok"] and not r["failed"] and not r["errors"])
a = answer(CASES["profile"])
check("checks were really run", review(a)["checks_run"] >= 8)

# 2) tampering is caught, and the damaged result is dropped


def tampered(case, change):
    bad = copy.deepcopy(answer(CASES[case]))
    change(bad["results"][0]["results"])
    return review(bad)


def caught(label, case, change, agent, expected):
    r = tampered(case, change)
    check(label, (not r["ok"]) and r["failed"] and r["failed"][0]["agent"] == agent and expected in r["failed"][0]["checks"]
          and r["facts"] == [])


caught("career runs changed", "profile", lambda x: x["career"]["data"]["batting"].__setitem__("runs", 8662),
       "player_analyst", "season runs add up to career runs")
caught("a phase changed", "profile", lambda x: x["phases"]["data"]["batting"]["death"].__setitem__("runs", 1),
       "player_analyst", "batting phase runs add up to career")
caught("scorecard wins changed", "compare", lambda x: x["scorecard"]["data"]["wins"].__setitem__("V Kohli", 9),
       "player_comparator", "wins plus ties equal the scored metrics")
caught("matchup runs changed", "matchup", lambda x: x["matchup"]["data"].__setitem__("runs", 186),
       "matchup_analyst", "matchup matches the batter-vs-bowler table")
caught("a by-year row changed", "opposition", lambda x: x["opposition"]["data"]["batting"]["by_year"][0].__setitem__("runs", 999),
       "opposition_analyst", "opposition: batting by-year totals add up")
caught("probabilities changed", "chase", lambda x: x["chase"]["data"].__setitem__("chase_win_prob", 0.91),
       "match_predictor", "probabilities add to 1")


def swap(x):
    rows = x["ranking"]["data"]["rows"]
    rows[0]["value"], rows[1]["value"] = rows[1]["value"], rows[0]["value"]


caught("leaderboard order changed", "leaderboard", swap, "leaderboard_analyst", "rows are sorted")

# 3) one bad result does not take down the good ones
mixed = copy.deepcopy(answer({"intents": ["opposition", "compare"], "players": ["kohli", "rohit sharma"], "teams": ["csk"]}))
mixed["results"][2]["results"]["scorecard"]["data"]["wins"]["V Kohli"] += 1
r = review(mixed)
check("good results are kept", r["ok"] and r["verified_agents"] == ["opposition_analyst", "opposition_analyst"])
check("the bad result is reported by name", [f["agent"] for f in r["failed"]] == ["player_comparator"] and len(r["facts"]) == 2)

# 4) failures and warnings
synthetic = {"results": [{"agent": "matchup_analyst", "ok": False, "errors": ["matchup: V Kohli has not faced X."],
                          "warnings": [], "insights": [], "results": {}, "index": 0}]}
r = review(synthetic)
check("agent errors are passed on", (not r["ok"]) and r["errors"] == ["matchup: V Kohli has not faced X."])
two = {"results": [dict(copy.deepcopy(answer(CASES["leaderboard"]))["results"][0], warnings=["only 5 players qualify"], index=i)
                   for i in range(2)]}
check("duplicate warnings are merged", review(two)["flags"] == ["only 5 players qualify"])
check("an empty answer is handled", review({})["ok"] is False and review(None)["ok"] is False)
check("an unknown agent fails closed", not review({"results": [{"agent": "mystery", "ok": True, "results": {}, "warnings": [],
                                                              "insights": [], "index": 0}]})["ok"])

# 5) the fact sheet
r = review(answer(CASES["profile"]))
text = json.dumps(r["facts"])
check("no player ids in the fact sheet", "player_id" not in text)
check("numbers are rounded to two decimals", all(abs(n * 100 - round(n * 100)) < 1e-6 for n in _numbers(r["facts"]) if isinstance(n, float)))
check("the fact sheet is a sensible size", len(text) < 40000)
ok = allowed_numbers(r["facts"])
check("Kohli's runs and best season are quotable", 8661 in ok and 973 in ok)
p = allowed_numbers(review(answer(CASES["chase"]))["facts"])
prob = answer(CASES["chase"])["results"][0]["results"]["chase"]["data"]["chase_win_prob"]
check("a probability can be quoted as a percentage", round(prob * 100) in p)
check("a number that is not in the facts is not allowed", 12345 not in ok)

print("\nfailures:", fails)

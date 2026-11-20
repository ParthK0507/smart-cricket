import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agents.summarize as S
from agents.critic import review
from agents.graph import ask
from agents.llm import USER_MESSAGE, LLMError, LLMUnavailable
from agents.plan import Understanding

fails = 0


def check(label, ok):
    global fails
    ok = bool(ok)
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}")


class Msg:
    def __init__(self, content):
        self.content = content


def script(*items):
    """Replace the model with a script: each item is a reply text, or an exception to raise."""
    calls, queue = [], list(items)

    def f(kind, prompt, schema=None, budget=20.0, max_tokens=1024):
        calls.append({"kind": kind, "prompt": prompt, "budget": budget})
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return Msg(item), [{"key": 1, "ok": True, "seconds": 0.1}]
    S.invoke_llm = f
    return calls


# ---- the number check on its own
facts = [{"data": {"career": {"runs": 8661, "avg": 39.57, "p": 0.693}}, "insights": []}]
fu = S.find_unsupported
check("quoted and rounded numbers pass", fu("He has 8,661 runs at an average of 39.6, about 40.", facts, "") == [])
check("a probability can be a percentage", fu("a 69% chance", facts, "") == [])
check("years are allowed", fu("in 2016 and 2024", facts, "") == [])
check("numbers from the question are allowed", fu("the top 7 players", facts, "top 7 sixes") == [])
check("structural numbers are allowed", fu("over 10 overs, the top 3", facts, "") == [])
check("5-wicket hauls are not flagged", fu("two 5-wicket hauls", facts, "") == [])
check("words with digits are ignored", fu("T20 cricket", facts, "") == [])
check("an invented number is caught", fu("scored 9,999 runs", facts, "") == [9999.0])
check("a wrong percentage is caught", fu("a 42% chance", facts, "") == [42.0])
check("scores such as 85/1 are checked", fu("85/1 after 10 overs", facts, "") == [85.0])
check("text cleaning removes code and trims", S._clean_text("```a```\n\n\n\nHello.") == "Hello."
      and len(S._clean_text("A sentence. " * 300)) <= 1800 and S._clean_text("A sentence. " * 300).endswith("."))

# ---- real verified facts
U = Understanding(intents=["compare"], players=["kohli", "raina"])
a = ask({"intents": ["compare"], "players": ["kohli", "raina"]})["answer"]
rv = review(a)
d = a["results"][0]["results"]["scorecard"]["data"]
n1, n2 = d["players"]
good = f"{n1} leads on {d['wins'][n1]} of the {d['scored_metrics']} scored metrics and {n2} on {d['wins'][n2]}."
bad = f"{n1} leads on 9999 metrics."

calls = script(good)
r = S.summarize("compare kohli and raina", rv, U)
check("a verified answer is returned", r["text"] == good and r["source"] == "model" and r["reason"] is None and r["unsupported"] == [])
p = calls[0]["prompt"]
check("the strong model is used", calls[0]["kind"] == "strong")
check("rules and question are separate messages", len(p) == 2 and "untrusted" in p[0].content)
check("the style for a comparison forbids a verdict", "Do not say who is the better player" in p[0].content)
check("the question sits in tags, the facts as JSON, no player ids",
      p[1].content.startswith("<question>") and "<facts>" in p[1].content and "player_id" not in p[1].content)

calls = script(good)
S.summarize("q", dict(rv, flags=["small sample: only 3 balls"]), U)
check("warning flags reach the model", "small sample" in calls[0]["prompt"][1].content)

calls = script(bad, good)
r = S.summarize("q", rv, U)
check("an unsupported number triggers one retry that succeeds", r["text"] == good and len(calls) == 2)
check("the retry names the offending number", "not in the facts" in calls[1]["prompt"][-1].content and "9999" in calls[1]["prompt"][-1].content)

calls = script(bad, bad)
r = S.summarize("q", rv, U)
check("still unsupported: no text, the numbers are reported",
      r["text"] is None and r["reason"] == "unsupported_numbers" and 9999.0 in r["unsupported"] and len(calls) == 2)

calls = script(LLMUnavailable("all_failed", [{"key": 1, "ok": False, "problem": "quota", "seconds": 1.0}]))
r = S.summarize("q", rv, U)
check("model unavailable: the dashboard message", r["text"] is None and r["reason"] == "unavailable"
      and r["notice"] == USER_MESSAGE and r["attempts"])
script(LLMError("bad"))
check("LLMError becomes 'unusable'", S.summarize("q", rv, U)["reason"] == "unusable")
script("")
check("an empty reply becomes 'unusable'", S.summarize("q", rv, U)["reason"] == "unusable")

calls = script("x")
check("no facts: no model call", S.summarize("q", {"facts": []}, U)["reason"] == "no_facts"
      and S.summarize("q", None, U)["reason"] == "no_facts" and calls == [])

calls = script(good)
S.summarize("q", rv, U, budget=14.0)
check("the time budget is passed on", 10 < calls[0]["budget"] <= 14.0)
calls = script(good)
r = S.summarize("q", rv, U, budget=2.0)
check("too little time: no call, the dashboard message", calls == [] and r["reason"] == "unavailable" and r["notice"] == USER_MESSAGE)

# ---- other kinds of answer: a text built from the real numbers passes, a wrong one is caught
lb = ask({"intents": ["leaderboard"], "metric": "runs", "top": 3})["answer"]
row = lb["results"][0]["results"]["ranking"]["data"]["rows"][0]
script(f"{row['player']} leads with {row['value']} runs.")
check("leaderboard text passes", S.summarize("top runs", review(lb), Understanding(intents=["leaderboard"]))["text"])
script(f"{row['player']} leads with {row['value'] + 1} runs.", f"{row['player']} leads with {row['value'] + 1} runs.")
check("a wrong leaderboard value is caught", S.summarize("top runs", review(lb), Understanding(intents=["leaderboard"]))["text"] is None)

mu = ask({"intents": ["matchup"], "players": ["kohli", "ashwin"]})["answer"]
m = mu["results"][0]["results"]["matchup"]["data"]
script(f"{m['batter']} scored {m['runs']} from {m['balls']} balls against {m['bowler']} and was dismissed {m['dismissals']} time.")
check("matchup text passes", S.summarize("kohli vs ashwin", review(mu), Understanding(intents=["matchup"]))["text"])

ch = ask({"intents": ["chase"], "teams": ["csk", "mi"], "venues": ["wankhede"], "first_innings_runs": 175})["answer"]
pr = ch["results"][0]["results"]["chase"]["data"]["chase_win_prob"]
script(f"The chasing team has a {round(pr * 100)}% chance, a model estimate.")
check("a probability written as a percentage passes", S.summarize("who wins", review(ch), Understanding(intents=["chase"]))["text"])
script("The chasing team has a 99% chance.", "The chasing team has a 99% chance.")
check("a wrong probability is caught", S.summarize("who wins", review(ch), Understanding(intents=["chase"]))["text"] is None)

print("\nfailures:", fails)

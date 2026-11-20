import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agents.service as S
from agents.graph import ask
from agents.guard import Guard
from agents.llm import USER_MESSAGE
from agents.plan import Understanding

fails = 0
calls = {"ask": 0, "sum": 0, "budget": None, "rv": None}


def check(label, ok):
    global fails
    ok = bool(ok)
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}")


def reset():
    calls.update(ask=0, sum=0, budget=None, rv=None)


def real(u, note=None, source="model"):
    return {"status": "answer", "answer": ask(u)["answer"], "understanding": Understanding(**u),
            "source": source, "note": note, "attempts": []}


def fake_ask(result):
    def f(q):
        calls["ask"] += 1
        return copy.deepcopy(result)
    return f


def fake_sum(text="Kohli leads on 6 of the 10 scored metrics.", reason=None):
    def f(q, rv, u=None, budget=14.0):
        calls.update(sum=calls["sum"] + 1, budget=budget, rv=rv)
        return {"text": text, "source": "model" if text else "none", "reason": reason, "unsupported": [],
                "attempts": [], "notice": None}
    return f


def boom(*a, **k):
    raise RuntimeError("boom")


CMP = {"intents": ["compare"], "players": ["kohli", "raina"]}
REAL_CMP = real(CMP)
orig_version, orig_budget = S._version, S.TOTAL_BUDGET

# ---- a normal answer
reset()
g = Guard()
S.answer_question, S.summarize = fake_ask(REAL_CMP), fake_sum()
r = S.answer("compare kohli and raina", "s1", g)
check("answer: status, text and source", r["status"] == "answer" and r["text"].startswith("Kohli leads") and r["source"] == "model" and not r["cached"])
check("answer: the verified results are shown", [x["agent"] for x in r["results"]] == ["player_comparator"] and r["failed"] == [] and r["notice"] is None)
check("answer: the summarizer got verified facts only", calls["rv"]["verified_agents"] == ["player_comparator"] and calls["rv"]["facts"])
check("answer: the time is reported", isinstance(r["seconds"], float))
check("answer: counted once by the guard", g.used_today()["count"] == 1)

# ---- the cache
r2 = S.answer("Compare Kohli and Raina?", "s2", g)
check("cache: the same question in other words is a hit", r2["cached"] and r2["text"] == r["text"] and calls["ask"] == 1 and calls["sum"] == 1)
check("cache: a hit is not counted against the limits", g.used_today()["count"] == 1)
r2["results"].clear()
check("cache: a caller cannot damage the cache", len(S.answer("compare kohli and raina", "s3", g)["results"]) == 1)
S._version = lambda: "new data"
S.answer("compare kohli and raina", "s1", g)
S._version = orig_version
check("cache: a new data version gives a fresh answer", calls["ask"] == 2)

# ---- the guard
reset()
g = Guard(per_minute=1)
S.answer_question, S.summarize = fake_ask(REAL_CMP), fake_sum()
S.answer("compare kohli and raina", "v", g)
lim = S.answer("top runs", "v", g)
check("limited: a second question within a minute", lim["status"] == "limited" and "wait about" in lim["message"] and calls["ask"] == 1)
hit = S.answer("compare kohli and raina", "v", g)
check("limited: a cached answer is still served", hit["status"] == "answer" and hit["cached"])

# ---- clarifying questions and plain messages
reset()
g = Guard()
S.answer_question = fake_ask({"status": "clarify", "message": "Which 'sharma' do you mean?", "understanding": None,
                              "source": "model", "note": None, "attempts": []})
a1, a2 = S.answer("sharma stats", "s", g), S.answer("sharma stats", "s", g)
check("clarify: the question is passed on", a1["status"] == "clarify" and "sharma" in a1["message"])
check("clarify: cached, and the summarizer is not used", a2["cached"] and calls["ask"] == 1 and calls["sum"] == 0)
reset()
g = Guard()
S.answer_question = fake_ask({"status": "message", "message": "Ask a question about IPL cricket."})
m1, m2 = S.answer("hmm", "s", g), S.answer("hmm", "s", g)
check("message: passed on and never cached", m1["status"] == "message" and "IPL" in m1["message"] and calls["ask"] == 2)
reset()
check("empty question: a message and no work", S.answer("   ", "s", g)["status"] == "message" and S.answer(None, "s", g)["status"] == "message" and calls["ask"] == 0)

# ---- the model is down
reset()
g = Guard()
S.answer_question, S.summarize = fake_ask(dict(REAL_CMP, note="model_unavailable", source="rules")), fake_sum()
t = S.answer("compare kohli and raina", "s", g)
check("model down: verified tables and the dashboard message",
      t["status"] == "tables_only" and t["message"] == USER_MESSAGE and t["notice"] == USER_MESSAGE and len(t["results"]) == 1 and t["source"] == "rules")
check("model down: the summarizer is not called", calls["sum"] == 0)
S.answer("compare kohli and raina", "s", g)
check("model down: not cached", calls["ask"] == 2)

# ---- the summarizer cannot deliver
for reason, word in [("unavailable", "dashboard"), ("unsupported_numbers", "verify"), ("unusable", "usable"), ("no_facts", "no numbers")]:
    reset()
    S.answer_question, S.summarize = fake_ask(REAL_CMP), fake_sum(text=None, reason=reason)
    x = S.answer("question " + reason, "s", Guard())
    check(f"summarizer {reason}: verified tables only", x["status"] == "tables_only" and word in x["message"].lower() and len(x["results"]) == 1)

# ---- failed verification
bad = copy.deepcopy(REAL_CMP)
bad["answer"]["results"][0]["results"]["scorecard"]["data"]["wins"]["V Kohli"] += 1
reset()
S.answer_question, S.summarize = fake_ask(bad), fake_sum()
x = S.answer("compare kohli and raina", "s", Guard())
check("failed checks: no answer and nothing shown",
      x["status"] == "message" and x["results"] == [] and x["failed"] == ["player_comparator"] and "verify" in x["message"].lower() and calls["sum"] == 0)

nf = real({"intents": ["matchup"], "players": ["SR Tendulkar", "Rashid Khan"]})
S.answer_question = fake_ask(nf)
x = S.answer("tendulkar vs rashid", "s", Guard())
check("an analyst error reaches the user in plain words", x["status"] == "message" and "has not faced" in x["message"])

mixed = real({"intents": ["opposition", "compare"], "players": ["kohli", "rohit sharma"], "teams": ["csk"]})
mixed["answer"]["results"][2]["results"]["scorecard"]["data"]["wins"]["V Kohli"] += 1
reset()
S.answer_question, S.summarize = fake_ask(mixed), fake_sum()
x = S.answer("kohli and rohit against csk and compare", "s", Guard())
check("partial failure: good results kept, the bad one reported",
      x["status"] == "answer" and [r["agent"] for r in x["results"]] == ["opposition_analyst", "opposition_analyst"]
      and x["failed"] == ["player_comparator"] and calls["rv"]["verified_agents"] == ["opposition_analyst", "opposition_analyst"])

# ---- time and failures
reset()
S.answer_question, S.summarize = fake_ask(REAL_CMP), fake_sum()
S.answer("question one", "s", Guard())
check("the summarizer gets at most 24 s", 0 < calls["budget"] <= 24.0)
S.TOTAL_BUDGET = 1.5
S.answer("question two", "s", Guard())
S.TOTAL_BUDGET = orig_budget
check("less total time means a smaller summarizer budget", calls["budget"] <= 1.5)

S.answer_question = boom
x = S.answer("anything", "s", Guard())
check("an exception becomes a message", x["status"] == "message" and "dashboard" in x["message"].lower())
S.answer_question, S.summarize = fake_ask(REAL_CMP), boom
x = S.answer("another question", "s", Guard())
check("a failing summarizer becomes tables only", x["status"] == "tables_only" and "usable" in x["message"].lower() and len(x["results"]) == 1)

print("\nfailures:", fails)

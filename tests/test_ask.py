import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agents.ask as A
from agents.plan import Understanding

fails, calls = 0, []


def check(label, ok):
    global fails
    ok = bool(ok)
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}")


def reply(u=None, source="model", message=None, note=None):
    def f(q, *a, **k):
        calls.append(q)
        return {"understanding": u, "source": source, "message": message, "note": note, "attempts": [], "question": q}
    return f


A.understand = reply(Understanding(intents=["compare"], players=["kohli", "raina"]))
r = A.answer_question("compare kohli and raina")
check("answer: status and analyst", r["status"] == "answer" and r["answer"]["agents"] == ["player_comparator"])
check("answer: the scorecard is right", r["answer"]["results"][0]["results"]["scorecard"]["data"]["scored_metrics"] == 10)
check("answer: source and understanding are passed on", r["source"] == "model" and r["understanding"].players == ["kohli", "raina"])

A.understand = reply(Understanding(intents=["compare"], players=["kohli", "raina"]), source="rules", note="the AI assistant is busy")
r = A.answer_question("compare kohli and raina")
check("answer from the keyword rules keeps its note", r["status"] == "answer" and r["source"] == "rules" and r["note"] == "the AI assistant is busy")

A.understand = reply(None, source="none", message="busy, use the dashboard pages")
r = A.answer_question("something the rules cannot read")
check("no understanding: the message is passed on", r["status"] == "message" and r["message"] == "busy, use the dashboard pages")

A.understand = reply(None, source="none", message=None)
check("no understanding and no message: the generic dashboard message",
      "dashboard" in A.answer_question("anything")["message"].lower())

A.understand = reply(Understanding(intents=["matchup"], players=["sharma", "bumrah"]))
r = A.answer_question("sharma against bumrah")
check("ambiguous name: a question for the user, nothing runs", r["status"] == "clarify" and "sharma" in r["message"].lower() and "answer" not in r)

A.understand = reply(Understanding(intents=["out_of_scope"]))
r = A.answer_question("what is the weather in pune")
check("out of scope: declined politely", r["status"] == "clarify" and "IPL" in r["message"])

A.understand = reply(Understanding(intents=["leaderboard"], metric="vibes"))
check("unknown statistic: a question for the user", A.answer_question("rank by vibes")["status"] == "clarify")

# input limits: no request is made for these
calls.clear()
A.understand = reply(Understanding(intents=["compare"], players=["kohli", "raina"]))
check("empty question", A.answer_question("   ")["status"] == "message" and A.answer_question(None)["status"] == "message")
long = A.answer_question("x" * 600)
check("too-long question is refused before any request", long["status"] == "message" and "500" in long["message"] and calls == [])

# failures never escape


def raising(*a, **k):
    raise RuntimeError("boom")


A.understand = raising
r = A.answer_question("anything")
check("understand() raising becomes a message", r["status"] == "message" and "dashboard" in r["message"].lower())

A.understand = reply(Understanding(intents=["compare"], players=["kohli", "raina"]))
real = A.run_graph
A.run_graph = raising
r = A.answer_question("compare kohli and raina")
check("the graph raising becomes a message", r["status"] == "message" and "dashboard" in r["message"].lower())
A.run_graph = lambda u: {}
check("a graph that returns nothing becomes a message", A.answer_question("compare kohli and raina")["status"] == "message")
A.run_graph = real

print("\nfailures:", fails)

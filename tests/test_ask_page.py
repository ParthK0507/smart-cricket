import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest

import agents.service as S
from agents.critic import review
from agents.graph import ask
from agents.llm import USER_MESSAGE

fails = 0
PAGE = str(ROOT / "app" / "pages" / "7_Ask.py")


def check(label, ok):
    global fails
    ok = bool(ok)
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}")


def real(u, status="answer", **kw):
    a = ask(u)["answer"]
    rv = review(a)
    return S._base("test question", status=status, text="A test answer." if status == "answer" else None,
                   results=a["results"], flags=rv["flags"], insights=rv["insights"], source="model", **kw)


def run_page(out, question="a question"):
    S.answer = lambda q, sid, *a, **k: out
    at = AppTest.from_file(PAGE, default_timeout=90)
    at.run()
    at.chat_input[0].set_value(question).run()
    return at


CASES = {
    "profile": ({"intents": ["player_profile"], "players": ["kohli"]}, True),
    "bowler profile": ({"intents": ["player_profile"], "players": ["bumrah"]}, True),
    "all-rounder profile": ({"intents": ["player_profile"], "players": ["jadeja"]}, True),
    "compare": ({"intents": ["compare"], "players": ["kohli", "raina"]}, True),
    "bowling compare": ({"intents": ["compare"], "players": ["bumrah", "malinga"]}, True),
    "opposition": ({"intents": ["opposition"], "players": ["kohli"], "teams": ["csk"]}, True),
    "all opponents": ({"intents": ["opposition"], "players": ["kohli"]}, False),
    "matchup": ({"intents": ["matchup"], "players": ["kohli", "ashwin"]}, True),
    "trend": ({"intents": ["trend"], "players": ["kohli"]}, True),
    "bowler trend": ({"intents": ["trend"], "players": ["bumrah"]}, True),
    "venue": ({"intents": ["venue"], "players": ["rohit sharma"], "venues": ["wankhede", "chepauk"]}, True),
    "chase": ({"intents": ["chase"], "teams": ["csk", "mi"], "venues": ["wankhede"], "first_innings_runs": 175}, True),
    "live": ({"intents": ["live"], "teams": ["csk", "mi"], "venues": ["wankhede"], "first_innings_runs": 180,
              "runs": 85, "wickets": 1, "balls_bowled": 60}, False),
    "preview": ({"intents": ["preview"], "teams": ["csk", "mi"], "venues": ["wankhede"]}, True),
    "leaderboard": ({"intents": ["leaderboard"], "metric": "runs", "top": 5}, True),
    "bowling leaderboard": ({"intents": ["leaderboard"], "metric": "economy", "role": "bowling", "top": 5}, True),
}
for label, (u, charts) in CASES.items():
    at = run_page(real(u))
    shown = any("A test answer." in m.value for m in at.markdown)
    check(f"{label}: the page draws without an error", (not at.exception) and shown and (not charts or len(at.get("plotly_chart")) > 0))

out = real(CASES["compare"][0], status="tables_only", message=USER_MESSAGE, notice=USER_MESSAGE)
at = run_page(out)
check("tables only: the dashboard message and the numbers",
      (not at.exception) and any(USER_MESSAGE in i.value for i in at.info) and len(at.get("plotly_chart")) > 0)

at = run_page(S._base("q", status="clarify", message="Which 'sharma' do you mean?"))
check("clarify: shown as a question", (not at.exception) and any("sharma" in i.value for i in at.info))
at = run_page(S._base("q", status="limited", message="You are asking quickly. Please wait about 30 seconds."))
check("limited: shown as a warning", (not at.exception) and any("wait about" in w.value for w in at.warning))
at = run_page(S._base("q", message="Please keep the question under 500 characters."))
check("message: shown as a warning", (not at.exception) and any("500" in w.value for w in at.warning))

out = real(CASES["compare"][0])
out["failed"] = ["player_comparator"]
out["flags"] = ["small sample: example"]
at = run_page(out)
check("a result that failed verification is reported", (not at.exception) and any("could not be verified" in w.value for w in at.warning))

at = run_page(real(CASES["profile"][0]))
at.chat_input[0].set_value("a second question").run()
check("the conversation keeps both exchanges", (not at.exception) and len(at.chat_message) == 4)

print("\nfailures:", fails)

"""Times the real summarizer in a fresh process. Needs keys; about 4 model requests.
Run:  python tests\\diag_summarizer.py"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agents.llm as L
from agents.ask import answer_question
from agents.critic import review
from agents.summarize import summarize

print("models:", L.MODELS, "| budgets:", L.MODEL_BUDGET, "| per key:", L.PER_KEY_SECONDS, "| keys:", L.status()["keys"])
q = "Compare Kohli and Raina"
r = answer_question(q)
print("understood by:", r.get("source"), "| status:", r["status"])
rv = review(r["answer"])
print("fact sheet characters:", sum(len(json.dumps(f, default=str)) for f in rv["facts"]))
for i in range(3):
    L.reset_state()
    t0 = time.monotonic()
    s = summarize(q, rv, r["understanding"])
    print(f"\nrun {i + 1}: {time.monotonic() - t0:.1f}s | source={s['source']} reason={s['reason']} unsupported={s['unsupported']}")
    for a in s["attempts"]:
        print("   ", a)
    print("   text:", (s["text"] or "")[:220])
    time.sleep(3)

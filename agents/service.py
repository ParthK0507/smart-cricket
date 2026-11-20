"""The Ask page's service: cache, guard, understanding, analysts, Critic, summarizer. Never raises."""
import copy
import time

from agents.ask import answer_question
from agents.critic import review
from agents.guard import DASHBOARDS, GUARD
from agents.llm import USER_MESSAGE
from agents.summarize import summarize
from core.data import table

CODE_VERSION = "1"        # bump when prompts or logic change, so cached answers are not reused
TOTAL_BUDGET = 36.0       # seconds for one whole question
UNVERIFIED = "I could not verify the numbers for that question, so I am not showing an answer. " + DASHBOARDS
TABLES_ONLY = {
    "unavailable": USER_MESSAGE,
    "unsupported_numbers": "I could not verify the wording of an answer, so here are the verified numbers instead. " + DASHBOARDS,
    "unusable": "The AI assistant did not give a usable answer, so here are the verified numbers instead. " + DASHBOARDS,
    "no_facts": "There were no numbers to summarise. " + DASHBOARDS,
}


def _version():
    return f"{table('matches')['date'].max().date()}|{CODE_VERSION}"


def _base(q, **kw):
    out = {"status": "message", "question": q, "text": None, "message": None, "notice": None, "results": [],
           "flags": [], "insights": [], "failed": [], "source": None, "cached": False, "seconds": 0.0}
    out.update(kw)
    return out


def _answer(q, session_id, guard, t0):
    if not q:
        return _base(q, message="Ask a question about IPL cricket.")
    version = _version()
    hit = guard.cache_get(q, version)
    if hit is not None:
        hit = copy.deepcopy(hit)
        hit["cached"] = True
        return hit
    ok, msg = guard.allow(session_id)
    if not ok:
        return _base(q, status="limited", message=msg)

    r = answer_question(q)
    if r["status"] == "message":
        return _base(q, message=r["message"])
    down = r.get("note") == "model_unavailable"
    if r["status"] == "clarify":
        out = _base(q, status="clarify", message=r["message"], source=r.get("source"), notice=USER_MESSAGE if down else None)
        if not down:
            guard.cache_put(q, out, version)
        return out

    a = r["answer"]
    rv = review(a)
    bad = {f["index"] for f in rv["failed"]}
    shown = [x for x in a["results"] if x.get("ok") and x.get("index") not in bad]
    common = dict(source=r.get("source"), results=shown, flags=rv["flags"], insights=rv["insights"],
                  failed=[f["agent"] for f in rv["failed"]], notice=USER_MESSAGE if down else None)
    if not rv["ok"]:
        errors = " ".join(dict.fromkeys(rv["errors"]))
        return _base(q, message=errors or UNVERIFIED, source=common["source"], flags=common["flags"],
                     failed=common["failed"], notice=common["notice"])
    if down:                                # the model is down: do not wait for it a second time
        return _base(q, status="tables_only", message=USER_MESSAGE, **common)

    left = TOTAL_BUDGET - (time.monotonic() - t0)
    try:
        s = summarize(q, rv, r["understanding"], budget=min(24.0, left))
    except Exception:
        s = {"text": None, "reason": "unusable"}
    if s.get("text"):
        out = _base(q, status="answer", text=s["text"], **common)
        guard.cache_put(q, out, version)
        return out
    return _base(q, status="tables_only", message=TABLES_ONLY.get(s.get("reason"), TABLES_ONLY["unusable"]), **common)


def answer(question, session_id, guard=GUARD):
    t0 = time.monotonic()
    q = " ".join(str(question or "").split())
    try:
        out = _answer(q, session_id, guard, t0)
    except Exception:
        out = _base(q, message="Something went wrong with that question. " + DASHBOARDS)
    out["seconds"] = round(time.monotonic() - t0, 1)
    return out

"""One entry point for the Ask page. The only code that reads understand()'s dictionary. Never raises."""
from agents.graph import ask as run_graph
from agents.understand import understand

MAX_QUESTION = 500
UNDERSTAND_BUDGET = 12.0      # seconds to wait for the model before falling back
GENERIC = ("Something went wrong with that question. You can get the same numbers from the dashboard pages in the "
           "sidebar: Player profile, Compare, Career timeline, Leaderboards, Matchups and Match predictor.")


def _message(text, **extra):
    return {"status": "message", "message": text, **extra}


def answer_question(question):
    """Returns {"status": "answer", "answer", "understanding", "source", "note", "attempts"}
    or {"status": "clarify", "message", ...} (a question for the user)
    or {"status": "message", "message", ...} (nothing to run: the dashboard pointer, an input problem)."""
    q = " ".join(str(question or "").split())
    if not q:
        return _message("Ask a question about IPL cricket.")
    if len(q) > MAX_QUESTION:
        return _message(f"Please keep the question under {MAX_QUESTION} characters.")

    try:
        r = understand(q, budget=UNDERSTAND_BUDGET)
    except Exception:
        return _message(GENERIC)
    u, attempts = r.get("understanding"), r.get("attempts", [])
    if u is None:
        return _message(r.get("message") or GENERIC, attempts=attempts)

    try:
        out = run_graph(u.model_dump())
    except Exception:
        return _message(GENERIC, attempts=attempts)
    meta = {"understanding": u, "source": r.get("source"), "note": r.get("note"), "attempts": attempts}
    if out.get("clarify"):
        return {"status": "clarify", "message": out["clarify"], **meta}
    if "answer" not in out:
        return _message(GENERIC, attempts=attempts)
    return {"status": "answer", "answer": out["answer"], **meta}

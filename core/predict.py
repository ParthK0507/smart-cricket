from functools import lru_cache

import joblib
import pandas as pd

from core.config import MODEL_DIR
from core.result import success, failure
from core.teams import resolve_team
from core.venues import resolve_venue

MODEL_PATH = MODEL_DIR / "chase_model.joblib"
MIN_RUNS, MAX_RUNS = 40, 300


@lru_cache(maxsize=1)
def _bundle():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"{MODEL_PATH} is missing. Run: python pipeline\\train_predictor.py")
    return joblib.load(MODEL_PATH)


def _chase_prob(x):
    """Chasing team's win probability when the first-innings score is x runs above par."""
    b = _bundle()
    return float(b["model"].predict_proba(pd.DataFrame({b["feature"]: [float(x)]}))[0, 1])


def _par_at(venue):
    s = _bundle()["par"]
    n = s["venue_n"].get(venue, 0)
    total = s["venue_sum"].get(venue, 0.0)
    return (total + s["k"] * s["league_mean"]) / (n + s["k"]), n


def _break_even(par):
    """First-innings score at which the chase is a 50-50 call."""
    lo, hi = -150.0, 150.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if _chase_prob(mid) > 0.5:
            lo = mid
        else:
            hi = mid
    return par + (lo + hi) / 2


def _team_or_error(text, label):
    r = resolve_team(text)
    if r["status"] == "ok":
        return r["team"], None
    msg = "Which team do you mean?" if r["status"] == "ambiguous" else "Team not found."
    return None, failure(f"{label}: {msg}", [{"team": c} for c in r["candidates"]])


def predict_chase(batting_first, chasing, venue, first_innings_runs):
    """Chasing team's win probability once the first innings is over."""
    bf, err = _team_or_error(batting_first, "batting first")
    if err:
        return err
    ch, err = _team_or_error(chasing, "chasing")
    if err:
        return err
    if bf == ch:
        return failure("The two teams must be different.")
    v = resolve_venue(venue)
    if v["status"] != "ok":
        msg = "Which ground do you mean?" if v["status"] == "ambiguous" else "Ground not found."
        return failure(msg, [{"venue": c} for c in v["candidates"]])
    try:
        runs = float(first_innings_runs)
    except (TypeError, ValueError):
        return failure("The first-innings score must be a number.")
    if not MIN_RUNS <= runs <= MAX_RUNS:
        return failure(f"The first-innings score must be between {MIN_RUNS} and {MAX_RUNS}.")

    ground = v["venue"]
    par, n_venue = _par_at(ground)
    x = runs - par
    p = _chase_prob(x)
    wf = _bundle()["report"]["walk_forward"]

    warnings = []
    if n_venue < 10:
        warnings.append(f"par score at {ground} rests on only {n_venue} earlier matches, so it leans on the league average")
    if abs(p - 0.5) < 0.05:
        warnings.append("this is close to a coin flip")

    data = {
        "batting_first": bf, "chasing": ch, "venue": ground, "first_innings_runs": runs,
        "par_score": round(par, 1), "target_vs_par": round(x, 1),
        "chase_win_prob": round(p, 3), "bat_first_win_prob": round(1 - p, 3),
        "favourite": ch if p >= 0.5 else bf,
        "break_even_score": round(_break_even(par), 1),
        "swing_per_10_runs": round(_chase_prob(x - 10) - p, 3),
        "matches_at_venue": n_venue,
        "model": {"accuracy": wf["accuracy"], "margin": wf["accuracy_margin"], "test_matches": wf["matches"],
                  "trained_through": _bundle()["report"]["trained_through"]},
        "notes": ["Only the first-innings score relative to the ground's par is used. Team strength, the toss, "
                  "weather and dew are not included, because they added no measurable accuracy in testing.",
                  "If the match was shortened by rain, use the revised target instead."],
    }
    scores = list(range(int(par) - 40, int(par) + 45, 5))
    chart = {"x": scores, "y": [round(_chase_prob(s - par), 3) for s in scores], "current": runs}
    return success(data, {"venue_matches": n_venue}, warnings, chart)

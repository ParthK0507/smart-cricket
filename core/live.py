from functools import lru_cache

import joblib
import pandas as pd

from core.config import MODEL_DIR
from core.predict import MAX_RUNS, MIN_RUNS, _par_at, _team_or_error, predict_chase
from core.result import failure, success
from core.venues import resolve_venue

LIVE_PATH = MODEL_DIR / "live_model.joblib"


@lru_cache(maxsize=1)
def _live():
    if not LIVE_PATH.exists():
        raise FileNotFoundError(f"{LIVE_PATH} is missing. Run: python pipeline\\train_live.py")
    return joblib.load(LIVE_PATH)


def _features(first_runs, par, runs, wickets, balls):
    needed = first_runs + 1 - runs
    left = 120 - balls
    return {"rrr": needed * 6 / left, "crr": runs * 6 / max(balls, 1), "wickets_in_hand": 10 - wickets,
            "balls_left": left, "runs_needed": needed, "target_vs_par": first_runs - par}


def _prob(feats):
    b = _live()
    return float(b["model"].predict_proba(pd.DataFrame([feats])[b["feats"]])[0, 1])


def predict_live(batting_first, chasing, venue, first_innings_runs, runs, wickets, balls_bowled):
    """Chasing team's win chance during the second innings of a full-length (20-over) chase."""
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
        first, runs, wickets, balls = int(first_innings_runs), int(runs), int(wickets), int(balls_bowled)
    except (TypeError, ValueError):
        return failure("The scores, wickets and balls bowled must be whole numbers.")
    if not MIN_RUNS <= first <= MAX_RUNS:
        return failure(f"The first-innings score must be between {MIN_RUNS} and {MAX_RUNS}.")
    if wickets >= 10:
        return failure("The chasing team is all out, so the chase is over.")
    if balls >= 120:
        return failure("All 20 overs have been bowled, so the chase is over.")
    if runs < 0 or wickets < 0 or balls < 0:
        return failure("Runs, wickets and balls bowled cannot be negative.")
    if runs >= first + 1:
        return failure("The chasing team has already reached the target.")

    b = _live()
    if balls < b["min_balls"]:                       # too early: the live model has nothing to add yet
        res = predict_chase(bf, ch, venue, first)
        if not res["ok"]:
            return res
        data = dict(res["data"], model_used="first-innings",
                    live_note="The live model starts once 3 overs have been bowled, so this is the first-innings estimate.")
        return success(data, res["sample"], res["warnings"], res["chart"])

    ground = v["venue"]
    par, n_venue = _par_at(ground)
    feats = _features(first, par, runs, wickets, balls)
    p = _prob(feats)

    wf = b["report"]["walk_forward"]
    row = max((r for r in wf if r["overs_done"] <= balls / 6), key=lambda r: r["overs_done"])

    nxt = []
    for r_next in (4, 8, 12, 16):
        for w_next in (0, 1):
            nr, nw, nb = runs + r_next, wickets + w_next, balls + 6
            if nb >= 120 or nw >= 10:
                continue
            pw = 1.0 if nr >= first + 1 else _prob(_features(first, par, nr, nw, nb))
            nxt.append({"next_over_runs": r_next, "wickets_in_over": w_next, "chase_win_prob": round(pw, 3)})

    warnings = []
    if n_venue < 10:
        warnings.append(f"par score at {ground} rests on only {n_venue} earlier matches")
    if abs(p - 0.5) < 0.05:
        warnings.append("this is close to a coin flip")
    if 0.1 <= p < 0.4:
        warnings.append("when the model gives the chasing team between 10% and 40%, chasing teams in testing won about "
                        "4 points more often than predicted, so treat this as slightly pessimistic")

    data = {
        "model_used": "live", "batting_first": bf, "chasing": ch, "venue": ground,
        "first_innings_runs": first, "target": first + 1, "score": f"{runs}/{wickets}",
        "overs": f"{balls // 6}.{balls % 6}", "runs_needed": feats["runs_needed"], "balls_left": feats["balls_left"],
        "wickets_in_hand": feats["wickets_in_hand"], "required_rate": round(feats["rrr"], 2),
        "current_rate": round(feats["crr"], 2), "par_score": round(par, 1),
        "chase_win_prob": round(p, 3), "bat_first_win_prob": round(1 - p, 3),
        "favourite": ch if p >= 0.5 else bf, "next_over": nxt,
        "model": {"accuracy": row["accuracy"], "margin": row["accuracy_margin"],
                  "test_states": row["states"], "at_overs": row["overs_done"],
                  "baseline_accuracy": row["baseline_accuracy"]},
    }
    return success(data, {"venue_matches": n_venue, "balls_bowled": balls}, warnings, None)

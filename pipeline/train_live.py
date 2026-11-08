"""Train the live chase model: win chance for the chasing team during the second innings.
Run from the project root:  python pipeline\\train_live.py
"""
import json
import sys
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.config import MODEL_DIR
from core.data import table
from pipeline.train_predictor import FIRST_TEST_YEAR, add_par, load_matches

FEATS = ["rrr", "crr", "wickets_in_hand", "balls_left", "runs_needed", "target_vs_par"]
CHECKPOINTS = (3, 6, 10, 15, 18)      # overs completed
MIN_BALLS = 18                        # the live model is used once 3 overs have been bowled


def build_snapshots():
    """One row per completed over of every full-length chase (rain-affected matches left out)."""
    d, _ = add_par(load_matches())
    d = d[~d["rain"]][["match_id", "year", "first_runs", "chase_win", "target_vs_par"]]
    b = table("balls")
    b = b[(b["innings"] == 2) & b["match_id"].isin(d["match_id"])].copy()
    w = table("wickets")
    w = w[(w["innings"] == 2) & w["counts_as_out"]]
    wk = w.groupby(["match_id", "over", "ball_in_over"]).size().rename("wk").reset_index()
    b = b.merge(wk, on=["match_id", "over", "ball_in_over"], how="left")
    b["wk"] = b["wk"].fillna(0)
    b["legal"] = b["is_legal"].astype(int)
    b = b.sort_values(["match_id", "over", "ball_in_over"])
    g = b.groupby("match_id")
    b["runs_so_far"], b["wkts"], b["balls_bowled"] = g["runs_total"].cumsum(), g["wk"].cumsum(), g["legal"].cumsum()
    s = (b.groupby(["match_id", "over"]).tail(1)[["match_id", "over", "runs_so_far", "wkts", "balls_bowled"]]
           .merge(d, on="match_id"))
    s["runs_needed"] = s["first_runs"] + 1 - s["runs_so_far"]
    s["balls_left"] = 120 - s["balls_bowled"]
    s["wickets_in_hand"] = 10 - s["wkts"]
    s = s[(s["runs_needed"] > 0) & (s["balls_left"] > 0) & (s["wickets_in_hand"] > 0)].copy()
    s["rrr"] = s["runs_needed"] * 6 / s["balls_left"]
    s["crr"] = s["runs_so_far"] * 6 / s["balls_bowled"].clip(lower=1)
    s["overs_done"] = s["over"] + 1
    return s.reset_index(drop=True)


def new_model():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000))


def walk_forward(s):
    """Train on earlier seasons, test on each season in turn; returns the pooled test states with both predictions."""
    parts = []
    for y in range(FIRST_TEST_YEAR, int(s["year"].max()) + 1):
        tr = s[(s["year"] < y) & (s["balls_bowled"] >= MIN_BALLS)]
        te = s[(s["year"] == y) & (s["balls_bowled"] >= MIN_BALLS)].copy()
        if te.empty:
            continue
        te["p_live"] = new_model().fit(tr[FEATS], tr["chase_win"]).predict_proba(te[FEATS])[:, 1]
        te["p_base"] = new_model().fit(tr[["target_vs_par"]], tr["chase_win"]).predict_proba(te[["target_vs_par"]])[:, 1]
        parts.append(te)
    return pd.concat(parts)


def main():
    MODEL_DIR.mkdir(exist_ok=True)
    s = build_snapshots()
    print(f"{len(s)} in-play snapshots from {s['match_id'].nunique()} full-length chases")

    t = walk_forward(s)
    print(f"\nWalk-forward test, {FIRST_TEST_YEAR} to {int(t['year'].max())}")
    print("overs done | states | live acc (+/-) | first-innings-only acc | live log loss | first-innings-only log loss")
    rows = []
    for k in CHECKPOINTS:
        c = t[t["overs_done"] == k]
        y = c["chase_win"]
        la, ba = ((c["p_live"] > .5) == y).mean(), ((c["p_base"] > .5) == y).mean()
        margin = 1.96 * np.sqrt(la * (1 - la) / len(c))
        ll, bl = log_loss(y, c["p_live"], labels=[0, 1]), log_loss(y, c["p_base"], labels=[0, 1])
        rows.append({"overs_done": k, "states": int(len(c)), "accuracy": round(float(la), 3),
                     "accuracy_margin": round(float(margin), 3), "baseline_accuracy": round(float(ba), 3),
                     "log_loss": round(float(ll), 3), "baseline_log_loss": round(float(bl), 3)})
        print(f"{k:10d} | {len(c):6d} | {la:.3f} (+/-{margin:.3f}) | {ba:.3f} | {ll:.3f} | {bl:.3f}")

    bins = pd.cut(t["p_live"], [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1])
    cal = (pd.DataFrame({"bin": bins, "pred": t["p_live"], "actual": t["chase_win"]})
           .groupby("bin", observed=True).agg(states=("actual", "size"), predicted=("pred", "mean"),
                                              actual=("actual", "mean")).round(3))
    print("\nCalibration over all test states (3+ overs bowled):")
    print(cal.to_string())

    train = s[s["balls_bowled"] >= MIN_BALLS]
    model = new_model().fit(train[FEATS], train["chase_win"])
    print("\nSanity: chasing 180 (par + 8) after 10 overs")
    for label, runs, wkts in [("60/1", 60, 1), ("85/1", 85, 1), ("85/3", 85, 3), ("85/5", 85, 5), ("85/7", 85, 7), ("110/1", 110, 1)]:
        row = pd.DataFrame([{"rrr": (180 - runs) * 6 / 60, "crr": runs * 6 / 60, "wickets_in_hand": 10 - wkts,
                             "balls_left": 60, "runs_needed": 180 - runs + 1, "target_vs_par": 8}])
        print(f"  {label:6} -> chase win {model.predict_proba(row[FEATS])[0, 1]:.2f}")

    report = {"version": 1, "trained_on": date.today().isoformat(), "snapshots": int(len(train)),
              "chases": int(train["match_id"].nunique()), "min_balls": MIN_BALLS, "features": FEATS,
              "walk_forward": rows, "calibration": cal.reset_index().astype({"bin": str}).to_dict("records")}
    joblib.dump({"model": model, "feats": FEATS, "min_balls": MIN_BALLS, "report": report}, MODEL_DIR / "live_model.joblib")
    (MODEL_DIR / "live_model_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("\nsaved", MODEL_DIR / "live_model.joblib")


if __name__ == "__main__":
    main()

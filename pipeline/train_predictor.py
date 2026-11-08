"""Train the 'after the first innings' chase model and save it with its honest accuracy.
Run from the project root:  python pipeline\\train_predictor.py
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

PAR_K, PAR_WINDOW, FIRST_TEST_YEAR = 5, 60, 2015
FEATURE = "target_vs_par"


def load_matches():
    m = table("matches")
    m = m[m["final_winner"].notna()].copy()                 # drops the no-result matches
    b = table("balls")
    first = (b[b["innings"] == 1].groupby("match_id")
               .agg(bat_first=("batting_team", "first"), first_runs=("runs_total", "sum")).reset_index())
    d = m.merge(first, on="match_id")
    d["chasing"] = np.where(d["bat_first"] == d["team1"], d["team2"], d["team1"])
    assert d["final_winner"].isin(d["bat_first"].tolist() + d["chasing"].tolist()).all()
    d["chase_win"] = (d["final_winner"] != d["bat_first"]).astype(int)
    d["rain"] = d["method"].notna()                         # rain-affected: the target was revised
    return d.sort_values("match_seq").reset_index(drop=True)


def add_par(d):
    """Par score at each ground, using ONLY earlier matches; also returns the final state for predictions."""
    venue_sum, venue_n, recent, pars = {}, {}, [], []
    for r in d.itertuples():
        league = float(np.mean(recent[-PAR_WINDOW:])) if recent else 160.0
        n, s = venue_n.get(r.venue, 0), venue_sum.get(r.venue, 0.0)
        pars.append((s + PAR_K * league) / (n + PAR_K))
        if not r.rain:
            venue_sum[r.venue], venue_n[r.venue] = s + r.first_runs, n + 1
            recent.append(r.first_runs)
    d = d.copy()
    d["par"] = pars
    d["target_vs_par"] = d["first_runs"] - d["par"]
    state = {"venue_sum": {k: float(v) for k, v in venue_sum.items()},
             "venue_n": {k: int(v) for k, v in venue_n.items()},
             "league_mean": float(np.mean(recent[-PAR_WINDOW:])), "k": PAR_K, "window": PAR_WINDOW}
    return d, state


def new_model():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))


def walk_forward(d):
    ps, ys, years = [], [], []
    for y in range(FIRST_TEST_YEAR, int(d["year"].max()) + 1):
        tr, te = d[(d["year"] < y) & ~d["rain"]], d[(d["year"] == y) & ~d["rain"]]
        if te.empty:
            continue
        p = new_model().fit(tr[[FEATURE]], tr["chase_win"]).predict_proba(te[[FEATURE]])[:, 1]
        ps += list(p); ys += list(te["chase_win"]); years += [y] * len(te)
    return np.array(ps), np.array(ys), np.array(years)


def main():
    MODEL_DIR.mkdir(exist_ok=True)
    d, state = add_par(load_matches())
    clean = d[~d["rain"]]
    print(f"{len(d)} matches, {int(d['rain'].sum())} rain-affected (left out of training) | "
          f"last match {d['date'].max().date()}")

    ps, ys, years = walk_forward(d)
    acc, ll = float(((ps > 0.5) == ys).mean()), float(log_loss(ys, ps))
    base = float(ys.mean())
    base_acc = max(base, 1 - base)
    margin = 1.96 * np.sqrt(acc * (1 - acc) / len(ys))
    print(f"\nWalk-forward test, {FIRST_TEST_YEAR} to {int(years.max())}: {len(ys)} matches")
    print(f"  accuracy {acc:.3f} (+/- {margin:.3f}) | log loss {ll:.3f} | always-majority accuracy {base_acc:.3f} | coin-flip log loss 0.693")

    bins = pd.cut(ps, [0, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0])
    cal = pd.DataFrame({"bin": bins, "pred": ps, "actual": ys}).groupby("bin", observed=True).agg(
        matches=("actual", "size"), predicted=("pred", "mean"), actual=("actual", "mean")).round(3)
    print("\nCalibration (predicted chase-win probability vs what happened):")
    print(cal.to_string())

    model = new_model().fit(clean[[FEATURE]], clean["chase_win"])
    print("\nChasing team's win probability by target vs par:")
    for x in (-30, -20, -10, 0, 10, 20, 30):
        print(f"  target {x:+d} runs vs par -> {model.predict_proba(pd.DataFrame({FEATURE: [x]}))[0, 1]:.2f}")

    report = {"version": 1, "trained_on": date.today().isoformat(), "trained_through": str(d["date"].max().date()),
              "matches_used": int(len(clean)), "rain_affected_excluded": int(d["rain"].sum()),
              "walk_forward": {"matches": int(len(ys)), "accuracy": round(acc, 3), "accuracy_margin": round(float(margin), 3),
                               "log_loss": round(ll, 3), "majority_accuracy": round(base_acc, 3)},
              "feature": FEATURE, "calibration": cal.reset_index().astype({"bin": str}).to_dict("records")}
    joblib.dump({"model": model, "feature": FEATURE, "par": state, "report": report}, MODEL_DIR / "chase_model.joblib")
    (MODEL_DIR / "chase_model_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("\nsaved", MODEL_DIR / "chase_model.joblib")


if __name__ == "__main__":
    main()

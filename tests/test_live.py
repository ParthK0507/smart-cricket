import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.live import _live, predict_live
from core.predict import _par_at

fails = 0


def check(label, ok):
    global fails
    ok = bool(ok)
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}")


def pl(first, runs, wk, balls, bf="csk", ch="mi", v="wankhede"):
    return predict_live(bf, ch, v, first, runs, wk, balls)


def p(*a):
    return pl(*a)["data"]["chase_win_prob"]


b = _live()
rows = sorted(b["report"]["walk_forward"], key=lambda r: r["overs_done"])
acc = [r["accuracy"] for r in rows]
check("report: accuracy rises through the chase", acc == sorted(acc) and acc[-1] > acc[0] + 0.10)
check("report: every checkpoint beats 65%", min(acc) > 0.65)
check("report: live model beats the first-innings-only model from over 6 on",
      all(r["accuracy"] > r["baseline_accuracy"] for r in rows if r["overs_done"] >= 6))

ps = [p(180, r, w, 60) for r, w in [(110, 1), (85, 1), (85, 3), (85, 5), (85, 7)]]
check("180 target after 10 overs: 110/1 > 85/1 > 85/3 > 85/5 > 85/7", ps == sorted(ps, reverse=True) and len(set(ps)) == 5)
wk = [p(180, 80, w, 60) for w in range(0, 9)]
check("more wickets lost means a lower chance", wk == sorted(wk, reverse=True))
rn = [p(180, r, 2, 60) for r in range(40, 150, 10)]
check("more runs scored means a higher chance", rn == sorted(rn))
check("need 3 off 6 balls with 7 wickets in hand is a strong favourite", p(150, 148, 3, 114) > 0.8)
check("need 101 off 6 balls with 1 wicket in hand is hopeless", p(180, 80, 9, 114) < 0.01)

d = pl(180, 85, 1, 60)["data"]
check("probabilities add to 1", round(d["chase_win_prob"] + d["bat_first_win_prob"], 3) == 1.0)
check("state fields: needed, balls left, wickets in hand",
      (d["runs_needed"], d["balls_left"], d["wickets_in_hand"], d["overs"], d["score"]) == (96, 60, 9, "10.0", "85/1"))
par, _ = _par_at("Wankhede Stadium, Mumbai")
f = {"rrr": 96 * 6 / 60, "crr": 85 * 6 / 60, "wickets_in_hand": 9, "balls_left": 60, "runs_needed": 96,
     "target_vs_par": 180 - par}
direct = float(b["model"].predict_proba(pd.DataFrame([f])[b["feats"]])[0, 1])
check("function matches the saved model computed by hand", abs(direct - d["chase_win_prob"]) < 0.001)

early, late = pl(170, 20, 0, 12)["data"], pl(170, 60, 1, 60)["data"]
check("under 3 overs falls back to the first-innings model", early["model_used"] == "first-innings" and "live_note" in early)
check("3 overs or more uses the live model", late["model_used"] == "live")
check("accuracy statement present and plausible", 0.65 < d["model"]["accuracy"] < 0.95 and d["model"]["test_states"] > 300)

nxt = pd.DataFrame(d["next_over"])
no_w, one_w = nxt[nxt["wickets_in_over"] == 0].sort_values("next_over_runs"), nxt[nxt["wickets_in_over"] == 1].sort_values("next_over_runs")
check("next over: more runs help", list(no_w["chase_win_prob"]) == sorted(no_w["chase_win_prob"]))
check("next over: a wicket always hurts",
      all(one_w.set_index("next_over_runs")["chase_win_prob"] < no_w.set_index("next_over_runs")["chase_win_prob"]))
check("a team that is behind gets the calibration warning", any("pessimistic" in w for w in pl(180, 85, 5, 60)["warnings"]))
check("a hopeless chase does not get it (the model is well calibrated there)", not any("pessimistic" in w for w in pl(180, 80, 9, 114)["warnings"]))

check("same team twice fails", not predict_live("csk", "csk", "wankhede", 180, 85, 1, 60)["ok"])
check("ambiguous team fails", not predict_live("gujarat", "mi", "wankhede", 180, 85, 1, 60)["ok"])
check("ambiguous ground fails", not predict_live("csk", "mi", "mumbai", 180, 85, 1, 60)["ok"])
check("target already reached fails", not pl(180, 181, 1, 60)["ok"])
check("all out fails", not pl(180, 85, 10, 60)["ok"])
check("20 overs bowled fails", not pl(180, 85, 1, 120)["ok"])
check("non-number fails", not pl(180, "abc", 1, 60)["ok"])

print("\nfailures:", fails)

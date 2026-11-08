import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.data import table
from core.predict import _bundle, predict_chase

fails = 0


def check(label, got, want=True):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got}" + ("" if ok else f"   (expected {want})"))


b = _bundle()
rep, par = b["report"], b["par"]
wf = rep["walk_forward"]
check("report: honest accuracy range", 0.62 <= wf["accuracy"] <= 0.74)
check("report: beats the always-majority baseline", wf["accuracy"] > wf["majority_accuracy"] + 0.08)
check("report: log loss beats a coin flip", wf["log_loss"] < 0.65)
check("par state covers every training match", sum(par["venue_n"].values()), rep["matches_used"])

m = table("matches")
w = m[(m["venue"] == "Wankhede Stadium, Mumbai") & m["final_winner"].notna() & m["method"].isna()]
check("Wankhede match count in par state", par["venue_n"]["Wankhede Stadium, Mumbai"], len(w))
sane = [(v, (par["venue_sum"][v] + par["k"] * par["league_mean"]) / (n + par["k"]))
        for v, n in par["venue_n"].items() if n >= 20]
check("par scores sane for grounds with 20+ matches", all(130 < p < 200 for _, p in sane))

probs = [predict_chase("csk", "mi", "wankhede", r)["data"]["chase_win_prob"] for r in range(100, 241, 10)]
check("higher target means lower chase probability", probs, sorted(probs, reverse=True))

r = predict_chase("csk", "mi", "wankhede", 175)
d = r["data"]
check("names resolve", (d["batting_first"], d["chasing"], d["venue"]),
      ("Chennai Super Kings", "Mumbai Indians", "Wankhede Stadium, Mumbai"))
check("probabilities add to 1", round(d["chase_win_prob"] + d["bat_first_win_prob"], 3), 1.0)
check("target_vs_par = score - par", round(175 - d["par_score"], 1), d["target_vs_par"])
at_even = predict_chase("csk", "mi", "wankhede", d["break_even_score"])["data"]["chase_win_prob"]
check("break-even score gives about 50%", abs(at_even - 0.5) < 0.01, True)
check("a bigger target helps the team batting first", d["swing_per_10_runs"] > 0)
check("chart curve falls as the score rises", r["chart"]["y"] == sorted(r["chart"]["y"], reverse=True))

check("same team twice fails", predict_chase("csk", "csk", "wankhede", 180)["ok"], False)
check("ambiguous team fails", predict_chase("gujarat", "mi", "wankhede", 180)["ok"], False)
check("ambiguous ground fails", predict_chase("csk", "mi", "mumbai", 180)["ok"], False)
check("unknown ground fails", predict_chase("csk", "mi", "xyzzy", 180)["ok"], False)
check("tiny score fails", predict_chase("csk", "mi", "wankhede", 10)["ok"], False)
check("non-number score fails", predict_chase("csk", "mi", "wankhede", "abc")["ok"], False)

print("\nfailures:", fails)

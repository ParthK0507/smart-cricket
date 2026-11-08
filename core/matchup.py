from core.data import table
from core.player import _who, _native, _not_found, _rows
from core.result import success, failure, small_sample


def _verdict(balls, outs, sr):
    """Heuristic label. The thresholds are easy to tune; the app always shows the numbers too."""
    if balls < 30:
        return "too few balls to judge"
    per_out = balls / outs if outs else None
    if (outs and per_out <= 18) or sr < 100:
        return "bowler on top"
    if sr >= 140 and (not outs or per_out >= 30):
        return "batter on top"
    return "even contest"


def get_bowler_matchup(batter, bowler):
    wb, wo = _who(batter), _who(bowler)
    for label, w in (("batter", wb), ("bowler", wo)):
        if w["status"] != "ok":
            res = _not_found(w)
            res["error"] = f"{label}: {res['error']}"
            return res
    b_name, o_name = wb["player"], wo["player"]

    h = table("batter_vs_bowler")
    row = h[(h["batter"] == b_name) & (h["bowler"] == o_name)]
    if row.empty:
        return failure(f"{b_name} has not faced {o_name} in the IPL.")
    r = row.iloc[0]
    runs, balls, outs = int(r["runs"]), int(r["balls"]), int(r["outs"])
    dots, fours, sixes = int(r["dots"]), int(r["fours"]), int(r["sixes"])
    if balls == 0:
        return failure(f"{b_name} has not faced a legal ball from {o_name}.")

    sr = runs / balls * 100
    data = {
        "batter": b_name, "bowler": o_name,
        "runs": runs, "balls": balls, "dismissals": outs,
        "strike_rate": round(sr, 2),
        "average": round(runs / outs, 2) if outs else None,
        "balls_per_dismissal": round(balls / outs, 1) if outs else None,
        "dot_pct": round(dots / balls * 100, 1),
        "fours": fours, "sixes": sixes,
        "boundary_run_pct": round((fours * 4 + sixes * 6) / runs * 100, 1) if runs else 0.0,
        "verdict": _verdict(balls, outs, sr),
    }

    # ---- breakdowns, rebuilt from the ball-by-ball table
    x = table("balls")
    x = x[(x["batter"] == b_name) & (x["bowler"] == o_name)]
    w = table("wickets")
    w = w[(w["player_out"] == b_name) & (w["bowler"] == o_name) & (w["bowler_wicket"])]

    def split(key):
        g = x.groupby(key).agg(runs=("runs_batter", "sum"), balls=("batter_ball_faced", "sum"),
                               dots=("bat_dot", "sum")).reset_index()
        o = w.groupby(key).size().rename("outs").reset_index()
        g = g.merge(o, on=key, how="left")
        g["outs"] = g["outs"].fillna(0).astype(int)
        g["sr"] = g["runs"] / g["balls"].where(g["balls"] > 0) * 100
        return g

    by_year, by_phase = split("year"), split("phase")
    data["by_year"] = _rows(by_year.sort_values("year"), ["year", "runs", "balls", "outs", "sr"])
    data["by_phase"] = _rows(by_phase, ["phase", "runs", "balls", "outs", "sr"])

    warnings = []
    wmsg = small_sample(balls, 30, "balls faced")
    if wmsg:
        warnings.append(wmsg)

    yr = by_year.sort_values("year")
    chart = {"x": yr["year"].astype(int).tolist(),
             "runs": yr["runs"].astype(int).tolist(),
             "sr": [_native(v) for v in yr["sr"]]}
    return success(data, {"balls": balls, "dismissals": outs}, warnings, chart)

from core.data import table
from core.player import _who, _native, _not_found, _rows, _frame_to_dict
from core.result import success, failure, small_sample
from core.venues import resolve_venue

PHASES = ["powerplay", "middle", "death"]


def _venue_or_error(venue):
    v = resolve_venue(venue)
    if v["status"] == "ok":
        return v["venue"], None
    msg = "Which ground do you mean?" if v["status"] == "ambiguous" else "Ground not found."
    return None, failure(msg, [{"venue": c} for c in v["candidates"]])


def get_venue_stats(player, venue):
    who = _who(player)
    if who["status"] != "ok":
        return _not_found(who)
    ven, err = _venue_or_error(venue)
    if err:
        return err
    name = who["player"]
    data = {"player": name, "player_id": who["player_id"], "venue": ven}
    sample, warnings, chart = {}, [], {}

    # ---------------- batting at this ground
    bat = table("player_match_batting")
    bat = bat[(bat["batter"] == name) & (bat["venue"] == ven)]
    if len(bat):
        ids = set(bat["match_id"])
        runs, balls, outs = int(bat["runs"].sum()), int(bat["balls"].sum()), int(bat["outs"].sum())
        career = table("career_batting")
        career = career[career["batter"] == name].iloc[0]
        top = bat.sort_values(["runs", "balls"], ascending=[False, True]).iloc[0]
        d = {
            "innings": len(bat), "runs": runs, "balls": balls, "outs": outs,
            "avg": round(runs / outs, 2) if outs else None,
            "sr": round(runs / balls * 100, 2) if balls else None,
            "high_score": int(top["runs"]), "high_score_not_out": bool(top["outs"] == 0),
            "fifties": int(((bat["runs"] >= 50) & (bat["runs"] < 100)).sum()),
            "hundreds": int((bat["runs"] >= 100).sum()),
            "ducks": int(((bat["runs"] == 0) & (bat["outs"] > 0)).sum()),
            "career_avg": _native(career["avg"]), "career_sr": _native(career["sr"]),
        }

        yr = (bat.groupby("year")
                 .agg(innings=("match_id", "count"), runs=("runs", "sum"),
                      balls=("balls", "sum"), outs=("outs", "sum")).reset_index())
        yr["avg"] = yr["runs"] / yr["outs"].where(yr["outs"] > 0)
        yr["sr"] = yr["runs"] / yr["balls"].where(yr["balls"] > 0) * 100
        d["by_year"] = _rows(yr, ["year", "innings", "runs", "balls", "outs", "avg", "sr"])

        x = table("balls")
        x = x[(x["batter"] == name) & (x["match_id"].isin(ids))]
        wk = table("wickets")
        wk = wk[(wk["player_out"] == name) & (wk["match_id"].isin(ids)) & wk["counts_as_out"]]
        g = (x.groupby("phase")
               .agg(runs=("runs_batter", "sum"), balls=("batter_ball_faced", "sum"), dots=("bat_dot", "sum"))
               .reindex(PHASES).fillna(0))
        g["outs"] = wk.groupby("phase").size().reindex(PHASES).fillna(0)
        g = g.fillna(0).astype(int)
        g["sr"] = g["runs"] / g["balls"].where(g["balls"] > 0) * 100
        g["avg"] = g["runs"] / g["outs"].where(g["outs"] > 0)
        d["by_phase"] = _frame_to_dict(g)

        data["batting"] = d
        sample["batting_innings"] = len(bat)
        chart["batting"] = {"x": yr["year"].astype(int).tolist(), "runs": yr["runs"].astype(int).tolist(),
                            "sr": [_native(v) for v in yr["sr"]]}
        w = small_sample(len(bat), 5, "batting innings at this ground")
        if w:
            warnings.append(w)

    # ---------------- bowling at this ground
    bowl = table("player_match_bowling")
    bowl = bowl[(bowl["bowler"] == name) & (bowl["venue"] == ven)]
    if len(bowl):
        ids = set(bowl["match_id"])
        balls, runs, wkts = int(bowl["balls"].sum()), int(bowl["runs"].sum()), int(bowl["wickets"].sum())
        career = table("career_bowling")
        career = career[career["bowler"] == name].iloc[0]
        best = bowl.sort_values(["wickets", "runs"], ascending=[False, True]).iloc[0]
        d = {
            "innings": len(bowl), "balls": balls, "runs": runs, "wickets": wkts,
            "economy": round(runs / (balls / 6), 2) if balls else None,
            "avg": round(runs / wkts, 2) if wkts else None,
            "sr": round(balls / wkts, 2) if wkts else None,
            "best_figures": f"{int(best['wickets'])}/{int(best['runs'])}",
            "career_economy": _native(career["economy"]),
        }

        yr = (bowl.groupby("year")
                  .agg(innings=("match_id", "count"), balls=("balls", "sum"),
                       runs=("runs", "sum"), wickets=("wickets", "sum")).reset_index())
        yr["economy"] = yr["runs"] / (yr["balls"].where(yr["balls"] > 0) / 6)
        d["by_year"] = _rows(yr, ["year", "innings", "balls", "runs", "wickets", "economy"])

        x = table("balls")
        x = x[(x["bowler"] == name) & (x["match_id"].isin(ids))]
        wk = table("wickets")
        wk = wk[(wk["bowler"] == name) & (wk["match_id"].isin(ids)) & wk["bowler_wicket"]]
        g = (x.groupby("phase").agg(balls=("is_legal", "sum"), runs=("bowler_runs", "sum"))
               .reindex(PHASES).fillna(0))
        g["wickets"] = wk.groupby("phase").size().reindex(PHASES).fillna(0)
        g = g.fillna(0).astype(int)
        g["economy"] = g["runs"] / (g["balls"].where(g["balls"] > 0) / 6)
        d["by_phase"] = _frame_to_dict(g)

        data["bowling"] = d
        sample["bowling_balls"] = balls
        chart["bowling"] = {"x": yr["year"].astype(int).tolist(), "wickets": yr["wickets"].astype(int).tolist(),
                            "economy": [_native(v) for v in yr["economy"]]}
        w = small_sample(balls, 60, "balls bowled at this ground")
        if w:
            warnings.append(w)

    if not sample:
        return failure(f"{name} has no IPL record at {ven}.")
    return success(data, sample, warnings, chart)

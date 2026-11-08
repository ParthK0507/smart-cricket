import numpy as np

from core.data import table
from core.resolve import resolve_player, _index
from core.result import success, failure, small_sample

BATTING_KEYS = ["innings", "runs", "balls", "outs", "high_score", "avg", "sr",
                "median_runs", "consistency", "contrib_rate", "fail_rate",
                "fifty_rate", "duck_rate", "first_year", "last_year", "seasons", "teams"]
BOWLING_KEYS = ["innings", "balls", "runs", "wickets", "economy", "spells",
                "median_economy", "wkt_rate", "exp_rate", "consistency",
                "first_year", "last_year", "seasons", "teams"]


def _native(v):
    """numpy types -> plain Python; NaN -> None."""
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return None if np.isnan(v) else round(float(v), 4)
    return v


def _record(row, keys):
    return {k: _native(row[k]) for k in keys}


def _who(player):
    """Accept a player id, a canonical name, or whatever the user typed."""
    idx = _index()
    by_id = idx[idx["player_id"] == player]
    if len(by_id):
        r = by_id.iloc[0]
        return {"status": "ok", "player": r["name"], "player_id": r["player_id"]}
    return resolve_player(player)


def get_career_stats(player):
    who = _who(player)
    if who["status"] != "ok":
        msg = "Which player do you mean?" if who["status"] == "ambiguous" else "Player not found."
        return failure(msg, who["candidates"])

    name = who["player"]
    data = {"player": name, "player_id": who["player_id"]}
    sample, warnings = {}, []

    # ---- batting
    cb = table("career_batting")
    cb = cb[cb["batter"] == name]
    if len(cb):
        bat = _record(cb.iloc[0], BATTING_KEYS)
        s = table("player_season_batting")
        s = s[s["batter"] == name]
        for col in ["fours", "sixes", "fifties", "hundreds"]:
            bat[col] = int(s[col].sum())
        data["batting"] = bat
        sample["batting_innings"] = bat["innings"]
        w = small_sample(bat["innings"], 10, "batting innings")
        if w:
            warnings.append(w)

    # ---- bowling
    cw = table("career_bowling")
    cw = cw[cw["bowler"] == name]
    if len(cw):
        bowl = _record(cw.iloc[0], BOWLING_KEYS)
        bowl["spells"] = int(bowl["spells"]) if bowl["spells"] is not None else 0
        wk = bowl["wickets"]
        bowl["avg"] = round(bowl["runs"] / wk, 2) if wk else None
        bowl["sr"] = round(bowl["balls"] / wk, 2) if wk else None
        s = table("player_season_bowling")
        s = s[s["bowler"] == name]
        bowl["three_w"] = int(s["three_w"].sum())
        bowl["five_w"] = int(s["five_w"].sum())
        m = table("player_match_bowling")
        m = m[m["bowler"] == name].sort_values(["wickets", "runs"], ascending=[False, True])
        best = m.iloc[0]
        bowl["best_figures"] = f"{int(best['wickets'])}/{int(best['runs'])}"
        data["bowling"] = bowl
        sample["bowling_balls"] = bowl["balls"]
        w = small_sample(bowl["balls"], 120, "balls bowled")
        if w:
            warnings.append(w)

    # ---- role label: a department only counts if the player did real work in it
    bat, bowl = data.get("batting"), data.get("bowling")
    bat_ok = bool(bat) and bat["runs"] >= 1000
    bowl_ok = bool(bowl) and bowl["wickets"] >= 30 and bowl["balls"] >= 600
    if bat_ok and bowl_ok:
        data["role"] = "all-rounder"
    elif bowl_ok:
        data["role"] = "bowler"
    elif bat_ok:
        data["role"] = "batter"
    else:                                   # too little of either: go by volume
        data["role"] = "bowler" if (bowl and bowl["balls"] > (bat or {}).get("balls", 0)) else "batter"

    return success(data, sample, warnings)

PHASES = ["powerplay", "middle", "death"]
INT_COLS = ["runs", "balls", "outs", "fours", "sixes", "dots"]


def _not_found(who):
    msg = "Which player do you mean?" if who["status"] == "ambiguous" else "Player not found."
    return failure(msg, who["candidates"])


def _rows(df, cols):
    return [{c: _native(v) for c, v in r.items()} for r in df[cols].to_dict("records")]


def _frame_to_dict(g):
    """DataFrame indexed by phase -> {phase: {column: value}}, keeping whole numbers whole."""
    return {ph: {c: _native(v) for c, v in zip(g.columns, vals)}
            for ph, vals in zip(g.index, g.itertuples(index=False, name=None))}


def get_season_stats(player):
    who = _who(player)
    if who["status"] != "ok":
        return _not_found(who)
    name = who["player"]
    data, sample, warnings, chart = {"player": name, "player_id": who["player_id"]}, {}, [], {}

    s = table("player_season_batting")
    s = s[s["batter"] == name].sort_values("year")
    if len(s):
        data["batting"] = _rows(s, ["year", "team", "innings", "runs", "balls", "outs",
                                    "high_score", "fifties", "hundreds", "avg", "sr"])
        best = s.loc[s["runs"].idxmax()]
        data["best_batting_season"] = {"year": int(best["year"]), "runs": int(best["runs"])}
        chart["batting"] = {"x": s["year"].astype(int).tolist(),
                            "runs": s["runs"].astype(int).tolist(),
                            "avg": [_native(v) for v in s["avg"]],
                            "sr": [_native(v) for v in s["sr"]]}
        sample["batting_seasons"] = len(s)
        thin = s.loc[s["innings"] < 5, "year"].astype(int).tolist()
        if thin:
            warnings.append(f"batting seasons with fewer than 5 innings: {thin}")

    b = table("player_season_bowling")
    b = b[b["bowler"] == name].sort_values("year")
    if len(b):
        data["bowling"] = _rows(b, ["year", "team", "innings", "balls", "runs", "wickets",
                                    "best_wkts", "economy", "avg", "sr"])
        best = b.loc[b["wickets"].idxmax()]
        data["best_bowling_season"] = {"year": int(best["year"]), "wickets": int(best["wickets"])}
        chart["bowling"] = {"x": b["year"].astype(int).tolist(),
                            "wickets": b["wickets"].astype(int).tolist(),
                            "economy": [_native(v) for v in b["economy"]]}
        sample["bowling_seasons"] = len(b)
        thin = b.loc[b["innings"] < 5, "year"].astype(int).tolist()
        if thin:
            warnings.append(f"bowling seasons with fewer than 5 innings: {thin}")

    if not sample:
        return failure("No IPL season data for this player.")
    return success(data, sample, warnings, chart)


def get_phase_stats(player, year=None):
    who = _who(player)
    if who["status"] != "ok":
        return _not_found(who)
    name = who["player"]
    data, sample, warnings = {"player": name, "player_id": who["player_id"], "year": year}, {}, []

    bp = table("batting_by_phase")
    bp = bp[bp["batter"] == name]
    if year is not None:
        bp = bp[bp["year"] == year]
    if len(bp):
        g = bp.groupby("phase")[INT_COLS].sum().reindex(PHASES).fillna(0)
        g[INT_COLS] = g[INT_COLS].astype(int)
        balls = g["balls"].where(g["balls"] > 0)
        g["sr"] = g["runs"] / balls * 100
        g["avg"] = g["runs"] / g["outs"].where(g["outs"] > 0)
        g["dot_pct"] = g["dots"] / balls * 100
        g["boundary_run_pct"] = (g["fours"] * 4 + g["sixes"] * 6) / g["runs"].where(g["runs"] > 0) * 100
        data["batting"] = _frame_to_dict(g)
        sample["batting_balls"] = int(g["balls"].sum())
        thin = [ph for ph in PHASES if g.loc[ph, "balls"] < 60]
        if thin:
            warnings.append(f"fewer than 60 balls faced in: {thin}")

    bw = table("bowling_by_phase")
    bw = bw[bw["bowler"] == name]
    if year is not None:
        bw = bw[bw["year"] == year]
    if len(bw):
        g = bw.groupby("phase")[["balls", "runs", "wickets"]].sum().reindex(PHASES).fillna(0)
        g = g.astype(int)
        balls = g["balls"].where(g["balls"] > 0)
        g["economy"] = g["runs"] / (balls / 6)
        g["avg"] = g["runs"] / g["wickets"].where(g["wickets"] > 0)
        g["sr"] = balls / g["wickets"].where(g["wickets"] > 0)
        data["bowling"] = _frame_to_dict(g)
        sample["bowling_balls"] = int(g["balls"].sum())
        thin = [ph for ph in PHASES if g.loc[ph, "balls"] < 60]
        if thin:
            warnings.append(f"fewer than 60 balls bowled in: {thin}")

    if not sample:
        return failure("No phase data for this player" + (f" in {year}." if year else "."))
    return success(data, sample, warnings)
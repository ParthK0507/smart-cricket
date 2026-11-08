from core.data import table
from core.player import _who, _not_found, get_career_stats, get_phase_stats
from core.result import success, failure
from core.trends import get_career_trends

MAX_PLAYERS = 4

# (key, higher_is_better, tie_tolerance, label)
BAT_METRICS = [
    ("avg", True, 0.5, "Batting average"),
    ("sr", True, 1.0, "Strike rate"),
    ("avg_vs_league", True, 0.5, "Average vs league (same seasons)"),
    ("sr_vs_league", True, 1.0, "Strike rate vs league (same seasons)"),
    ("consistency", True, 1.0, "Consistency index"),
    ("fail_rate", False, 0.01, "Low-score rate (out under 10)"),
    ("peak_runs_per_inn", True, 1.0, "Best season (runs per innings)"),
    ("pp_sr", True, 2.0, "Powerplay strike rate"),
    ("mid_sr", True, 2.0, "Middle-overs strike rate"),
    ("death_sr", True, 3.0, "Death-overs strike rate"),
]
BOWL_METRICS = [
    ("economy", False, 0.1, "Economy"),
    ("avg", False, 1.0, "Bowling average"),
    ("sr", False, 1.0, "Strike rate (balls per wicket)"),
    ("econ_vs_league", False, 0.1, "Economy vs league (same seasons)"),
    ("consistency", True, 1.0, "Consistency index"),
    ("wkts_per_inn", True, 0.02, "Wickets per innings"),
    ("peak_wkts_per_inn", True, 0.05, "Best season (wickets per innings)"),
    ("pp_econ", False, 0.15, "Powerplay economy"),
    ("mid_econ", False, 0.15, "Middle-overs economy"),
    ("death_econ", False, 0.2, "Death-overs economy"),
]
BAT_CONTEXT = ["innings", "runs", "balls", "high_score", "fifties", "hundreds", "seasons",
               "first_year", "last_year", "teams", "balls_per_innings"]
BOWL_CONTEXT = ["innings", "balls", "wickets", "best_figures", "five_w", "seasons",
                "first_year", "last_year", "teams", "balls_per_innings"]
BAT_RADAR = ["avg", "sr", "consistency", "pp_sr", "mid_sr", "death_sr", "peak_runs_per_inn"]
BOWL_RADAR = ["economy", "avg", "wkts_per_inn", "consistency", "pp_econ", "death_econ"]


def _batting_row(name):
    c = get_career_stats(name)["data"]["batting"]
    ph = get_phase_stats(name)["data"]["batting"]
    ev = get_career_trends(name)["data"]["batting"]["events"]
    s = table("player_season_batting")
    s = s[s["batter"] == name]
    lg = table("player_season_batting").groupby("year")[["runs", "balls", "outs"]].sum()
    lg_sr, lg_avg = lg["runs"] / lg["balls"] * 100, lg["runs"] / lg["outs"]
    yrs = s["year"].tolist()
    exp_sr = float((lg_sr.loc[yrs].values * s["balls"].values).sum() / s["balls"].sum())
    outs_total = s["outs"].sum()
    exp_avg = float((lg_avg.loc[yrs].values * s["outs"].values).sum() / outs_total) if outs_total else None
    row = {k: c[k] for k in ["innings", "runs", "balls", "high_score", "fifties", "hundreds", "seasons",
                             "first_year", "last_year", "teams", "avg", "sr", "consistency", "fail_rate"]}
    row.update({
        "balls_per_innings": round(c["balls"] / c["innings"], 1),
        "peak_runs_per_inn": ev["best_season"]["value"] if ev else None,
        "pp_sr": ph["powerplay"]["sr"], "mid_sr": ph["middle"]["sr"], "death_sr": ph["death"]["sr"],
        "avg_vs_league": round(c["avg"] - exp_avg, 2) if (c["avg"] is not None and exp_avg is not None) else None,
        "sr_vs_league": round(c["sr"] - exp_sr, 2),
    })
    return row, set(yrs)


def _bowling_row(name):
    c = get_career_stats(name)["data"]["bowling"]
    ph = get_phase_stats(name)["data"]["bowling"]
    ev = get_career_trends(name)["data"].get("bowling", {}).get("events")
    s = table("player_season_bowling")
    s = s[s["bowler"] == name]
    lg = table("player_season_bowling").groupby("year")[["runs", "balls"]].sum()
    lg_econ = lg["runs"] / (lg["balls"] / 6)
    yrs = s["year"].tolist()
    exp_econ = float((lg_econ.loc[yrs].values * s["balls"].values).sum() / s["balls"].sum())
    row = {k: c[k] for k in ["innings", "balls", "wickets", "best_figures", "five_w", "seasons",
                             "first_year", "last_year", "teams", "avg", "sr", "economy", "consistency"]}
    row.update({
        "balls_per_innings": round(c["balls"] / c["innings"], 1),
        "wkts_per_inn": round(c["wickets"] / c["innings"], 3),
        "peak_wkts_per_inn": ev["best_season"]["value"] if ev else None,
        "pp_econ": ph["powerplay"]["economy"], "mid_econ": ph["middle"]["economy"],
        "death_econ": ph["death"]["economy"],
        "econ_vs_league": round(c["economy"] - exp_econ, 2),
    })
    return row, set(yrs)


def _score(rows, names, spec):
    metrics, wins, ties, scored = {}, {n: 0 for n in names}, 0, 0
    for key, higher, tol, label in spec:
        vals = {n: rows[n][key] for n in names}
        entry = {"label": label, "higher_is_better": higher, "values": vals, "winner": "n/a"}
        if all(v is not None for v in vals.values()):
            scored += 1
            best = max(vals.values()) if higher else min(vals.values())
            leaders = [n for n, v in vals.items() if abs(v - best) <= tol]
            if len(leaders) == 1:
                entry["winner"] = leaders[0]
                wins[leaders[0]] += 1
            else:
                entry["winner"] = "tie"
                ties += 1
        metrics[key] = entry
    return metrics, wins, ties, scored


def _radar(rows, names, keys, spec):
    higher = {k: h for k, h, _, _ in spec}
    series = {n: [] for n in names}
    for k in keys:
        vals = {n: rows[n][k] for n in names}
        if any(v is None or v <= 0 for v in vals.values()):
            for n in names:
                series[n].append(None)
            continue
        best = max(vals.values()) if higher[k] else min(vals.values())
        for n, v in vals.items():
            series[n].append(round(v / best if higher[k] else best / v, 3))
    return {"axes": keys, "series": series}


def compare_players(players, role="auto"):
    if not isinstance(players, (list, tuple)) or not (2 <= len(players) <= MAX_PLAYERS):
        return failure(f"Give between 2 and {MAX_PLAYERS} players to compare.")
    resolved = []
    for p in players:
        w = _who(p)
        if w["status"] != "ok":
            res = _not_found(w)
            res["error"] = f"'{p}': {res['error']}"
            return res
        resolved.append(w)
    names = [w["player"] for w in resolved]
    if len(set(names)) != len(names):
        return failure("The same player was given twice.")

    roles = {n: get_career_stats(n)["data"]["role"] for n in names}
    chosen = role if role in ("batting", "bowling") else None
    if chosen is None:
        if all(r in ("batter", "all-rounder") for r in roles.values()):
            chosen = "batting"
        elif all(r in ("bowler", "all-rounder") for r in roles.values()):
            chosen = "bowling"
        else:
            return failure("These players have different roles; choose role='batting' or role='bowling'.",
                           [{"player": n, "role": r} for n, r in roles.items()])

    key = "batting" if chosen == "batting" else "bowling"
    for n in names:
        if not get_career_stats(n)["data"].get(key):
            return failure(f"{n} has no {chosen} record in the IPL.")

    build = _batting_row if chosen == "batting" else _bowling_row
    spec = BAT_METRICS if chosen == "batting" else BOWL_METRICS
    ctx_keys = BAT_CONTEXT if chosen == "batting" else BOWL_CONTEXT
    radar_keys = BAT_RADAR if chosen == "batting" else BOWL_RADAR

    rows, years = {}, {}
    for n in names:
        rows[n], years[n] = build(n)

    metrics, wins, ties, scored = _score(rows, names, spec)
    overlap = set.intersection(*years.values())

    warnings = []
    for n in names:
        if rows[n]["innings"] < 30:
            warnings.append(f"small sample: {n} has only {rows[n]['innings']} {chosen} innings")
    bpi = {n: rows[n]["balls_per_innings"] for n in names}
    lo, hi = min(bpi, key=bpi.get), max(bpi, key=bpi.get)
    if bpi[hi] > 1.5 * bpi[lo]:
        warnings.append(f"different roles: balls per innings is {bpi[lo]} for {lo} but {bpi[hi]} for {hi}")
    if len(overlap) < 3:
        warnings.append(f"played in different eras: only {len(overlap)} season(s) in common, "
                        "so the vs-league rows matter most")

    data = {
        "role": chosen, "players": names, "player_ids": {w["player"]: w["player_id"] for w in resolved},
        "roles": roles, "metrics": metrics, "wins": wins, "ties": ties, "scored_metrics": scored,
        "context": {k: {n: rows[n][k] for n in names} for k in ctx_keys},
        "overlap_seasons": sorted(int(y) for y in overlap),
    }
    sample = {"players": len(names), "min_innings": min(rows[n]["innings"] for n in names)}
    return success(data, sample, warnings, {"radar": _radar(rows, names, radar_keys, spec)})

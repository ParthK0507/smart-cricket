from core.data import table
from core.player import _native
from core.resolve import _index
from core.result import success, failure
from core.teams import resolve_team
from core.venues import resolve_venue

# metric -> (label, higher_is_better, is_rate)
BAT_METRICS = {
    "runs": ("Runs", True, False), "avg": ("Batting average", True, True), "sr": ("Strike rate", True, True),
    "fours": ("Fours", True, False), "sixes": ("Sixes", True, False), "fifties": ("Fifties", True, False),
    "hundreds": ("Hundreds", True, False), "high_score": ("High score", True, False),
    "ducks": ("Ducks", True, False), "consistency": ("Consistency index", True, True),
}
BOWL_METRICS = {
    "wickets": ("Wickets", True, False), "economy": ("Economy", False, True),
    "avg": ("Bowling average", False, True), "sr": ("Bowling strike rate", False, True),
    "three_w": ("3+ wicket hauls", True, False), "five_w": ("5-wicket hauls", True, False),
    "dots": ("Dot balls", True, False), "consistency": ("Consistency index", True, True),
}
BAT_COLS = ["innings", "runs", "balls", "outs", "avg", "sr", "fours", "sixes", "fifties",
            "hundreds", "high_score", "ducks", "consistency"]
BOWL_COLS = ["innings", "balls", "runs", "wickets", "economy", "avg", "sr", "three_w", "five_w",
             "dots", "consistency"]


def _resolve_filter(label, text):
    r = resolve_venue(text) if label == "venue" else resolve_team(text)
    if r["status"] == "ok":
        return r["venue" if label == "venue" else "team"], None
    what = "ground" if label == "venue" else "team"
    msg = f"Which {what} do you mean?" if r["status"] == "ambiguous" else f"{what.capitalize()} not found."
    return None, failure(msg, [{what: c} for c in r["candidates"]])


def _agg_batting(df):
    d = df.copy()
    dismissed = d["outs"] > 0
    d["contrib"] = (d["runs"] >= 20) | ((d["runs"] >= 10) & (d["strike_rate"] >= 150))
    d["fail"] = (d["runs"] < 10) & dismissed
    d["fifty"] = (d["runs"] >= 50) & (d["runs"] < 100)
    d["hundred"] = d["runs"] >= 100
    d["duck"] = (d["runs"] == 0) & dismissed
    g = d.groupby("batter").agg(
        innings=("runs", "size"), runs=("runs", "sum"), balls=("balls", "sum"), outs=("outs", "sum"),
        fours=("fours", "sum"), sixes=("sixes", "sum"), fifties=("fifty", "sum"), hundreds=("hundred", "sum"),
        ducks=("duck", "sum"), high_score=("runs", "max"), contrib=("contrib", "mean"),
        fail=("fail", "mean")).reset_index()
    g["avg"] = g["runs"] / g["outs"].where(g["outs"] > 0)
    g["sr"] = g["runs"] / g["balls"].where(g["balls"] > 0) * 100
    g["consistency"] = 100 * (0.6 * g["contrib"] + 0.4 * (1 - g["fail"]))
    return g.rename(columns={"batter": "player"}).drop(columns=["contrib", "fail"])


def _agg_bowling(df):
    d = df.copy()
    d["three"], d["five"] = d["wickets"] >= 3, d["wickets"] >= 5
    g = d.groupby("bowler").agg(
        innings=("balls", "size"), balls=("balls", "sum"), runs=("runs", "sum"), wickets=("wickets", "sum"),
        dots=("dots", "sum"), three_w=("three", "sum"), five_w=("five", "sum")).reset_index()
    sp = d[d["balls"] >= 12].copy()
    sp["took"], sp["exp"] = sp["wickets"] >= 1, sp["economy"] >= 10
    r = sp.groupby("bowler").agg(wkt_rate=("took", "mean"), exp_rate=("exp", "mean")).reset_index()
    g = g.merge(r, on="bowler", how="left")
    g["economy"] = g["runs"] / (g["balls"].where(g["balls"] > 0) / 6)
    g["avg"] = g["runs"] / g["wickets"].where(g["wickets"] > 0)
    g["sr"] = g["balls"] / g["wickets"].where(g["wickets"] > 0)
    g["consistency"] = 100 * (0.5 * g["wkt_rate"] + 0.5 * (1 - g["exp_rate"]))
    return g.rename(columns={"bowler": "player"}).drop(columns=["wkt_rate", "exp_rate"])


def get_leaderboard(metric, role="batting", top=10, year=None, year_from=None, year_to=None,
                    team=None, opposition=None, venue=None, min_innings=None):
    if role not in ("batting", "bowling"):
        return failure("role must be 'batting' or 'bowling'.")
    spec = BAT_METRICS if role == "batting" else BOWL_METRICS
    if metric not in spec:
        return failure(f"Unknown {role} metric '{metric}'. Choose from: {sorted(spec)}")
    try:
        top = int(top)
        year = None if year is None else int(year)
        year_from = None if year_from is None else int(year_from)
        year_to = None if year_to is None else int(year_to)
    except (TypeError, ValueError):
        return failure("top and the years must be whole numbers.")
    if not 1 <= top <= 1000:
        return failure("top must be between 1 and 1000.")
    label, higher, is_rate = spec[metric]

    if role == "batting":
        df, team_col = table("player_match_batting"), "batting_team"
    else:
        df, team_col = table("player_match_bowling"), "team"

    filters = {}
    if year is not None:
        df, filters["year"] = df[df["year"] == year], year
    if year_from is not None:
        df, filters["year_from"] = df[df["year"] >= year_from], year_from
    if year_to is not None:
        df, filters["year_to"] = df[df["year"] <= year_to], year_to
    for name, text, col in (("team", team, team_col), ("opposition", opposition, "opposition"),
                            ("venue", venue, "venue")):
        if text:
            val, err = _resolve_filter(name, text)
            if err:
                return err
            df, filters[name] = df[df[col] == val], val
    if df.empty:
        return failure("No IPL data matches these filters.")

    if min_innings is None:
        min_innings = 8 if year is not None else (5 if filters else 20)
    min_innings = int(min_innings)
    min_balls = 12 * min_innings if role == "bowling" else None

    g = _agg_batting(df) if role == "batting" else _agg_bowling(df)
    if is_rate:
        g = g[g["innings"] >= min_innings]
        if role == "bowling":
            g = g[g["balls"] >= min_balls]
        g = g.dropna(subset=[metric])
    else:
        g = g[g[metric] > 0]
    if g.empty:
        return failure("No players qualify for this leaderboard.")

    g = g.sort_values([metric, "innings", "player"], ascending=[not higher, False, True])
    qualified = len(g)
    ids = _index().set_index("name")["player_id"].to_dict()
    cols = BAT_COLS if role == "batting" else BOWL_COLS
    rows = [{"rank": i + 1, "player": r["player"], "player_id": ids.get(r["player"]),
             "value": _native(r[metric]), **{c: _native(r[c]) for c in cols}}
            for i, r in enumerate(g.head(top).to_dict("records"))]

    warnings = []
    if qualified < top:
        warnings.append(f"only {qualified} player(s) qualify")
    data = {"role": role, "metric": metric, "label": label, "higher_is_better": higher,
            "filters": filters, "min_innings": min_innings if is_rate else None,
            "min_balls": min_balls if is_rate else None, "qualified": qualified, "rows": rows}
    chart = {"x": [r["player"] for r in rows], "y": [r["value"] for r in rows], "label": label}
    return success(data, {"players_ranked": qualified, "matches": int(df["match_id"].nunique())}, warnings, chart)

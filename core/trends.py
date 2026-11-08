import numpy as np

from core.data import table
from core.player import _who, _native, _not_found, _rows
from core.result import success, failure

MIN_INN = 6     # a season needs at least this many innings to count for peaks and slumps
WINDOW = 10     # innings in a "form window"


def _team_spans(s):
    spans = []
    for y, t in zip(s["year"], s["team"]):
        if spans and spans[-1]["team"] == t:
            spans[-1]["to_year"] = int(y)
        else:
            spans.append({"team": t, "from_year": int(y), "to_year": int(y)})
    return spans


def _events(s, col, label):
    """Peaks and slumps on one per-season column (needs 'year' and col)."""
    s = s.sort_values("year").reset_index(drop=True)
    if len(s) < 3:
        return None
    mu, sd = s[col].mean(), s[col].std()
    z = (s[col] - mu) / sd if sd and sd > 0 else s[col] * 0
    best, worst = s.loc[s[col].idxmax()], s.loc[s[col].idxmin()]
    diff = s[col].diff()
    j, k = diff.idxmax(), diff.idxmin()
    return {
        "metric": label, "career_mean": round(float(mu), 2),
        "best_season": {"year": int(best["year"]), "value": round(float(best[col]), 2)},
        "worst_season": {"year": int(worst["year"]), "value": round(float(worst[col]), 2)},
        "peak_years": s.loc[z >= 1, "year"].astype(int).tolist(),
        "slump_years": s.loc[z <= -1, "year"].astype(int).tolist(),
        "biggest_jump": {"from_year": int(s.loc[j - 1, "year"]), "to_year": int(s.loc[j, "year"]),
                         "change": round(float(diff[j]), 2)},
        "biggest_drop": {"from_year": int(s.loc[k - 1, "year"]), "to_year": int(s.loc[k, "year"]),
                         "change": round(float(diff[k]), 2)},
    }


def _league_sr(years):
    s = table("player_season_batting").groupby("year")[["runs", "balls"]].sum().loc[[int(y) for y in years]]
    return float(s["runs"].sum() / s["balls"].sum() * 100)


def _league_econ(years):
    s = table("player_season_bowling").groupby("year")[["runs", "balls"]].sum().loc[[int(y) for y in years]]
    return float(s["runs"].sum() / (s["balls"].sum() / 6))


# ---------------------------------------------------------------- batting helpers
def _bat_agg(df):
    runs, balls, outs = int(df["runs"].sum()), int(df["balls"].sum()), int(df["outs"].sum())
    return {"runs": runs,
            "avg": round(runs / outs, 2) if outs else None,
            "sr": round(runs / balls * 100, 2) if balls else None}


def _bat_window(bat, pick):
    r = bat["runs"].rolling(WINDOW).sum()
    if r.notna().sum() == 0:
        return None
    i = int(r.idxmax() if pick == "best" else r.idxmin())
    w = bat.iloc[i - WINDOW + 1: i + 1]
    return {"from": str(w["date"].iloc[0].date()), "to": str(w["date"].iloc[-1].date()),
            "innings": len(w), **_bat_agg(w)}


def _bat_trend(q):
    """Recent 3 seasons vs earlier ones, judged against how the whole league moved."""
    if len(q) < 4:
        return None
    slope = float(np.polyfit(q["year"].astype(float), q["sr"].astype(float), 1)[0])
    recent, earlier = q.tail(3), q.iloc[:-3]
    r, e = _bat_agg(recent), _bat_agg(earlier)
    raw = round(r["sr"] - e["sr"], 2)
    league = round(_league_sr(recent["year"]) - _league_sr(earlier["year"]), 2)
    rel = round(raw - league, 2)
    label = lambda v: "improved" if v >= 5 else ("declined" if v <= -5 else "steady")
    return {"sr_slope_per_year": round(slope, 2), "recent_years": recent["year"].astype(int).tolist(),
            "recent": r, "earlier": e, "sr_change": raw, "league_sr_change": league,
            "relative_change": rel, "direction": label(rel), "direction_raw": label(raw)}


# ---------------------------------------------------------------- bowling helpers
def _bowl_agg(df, innings):
    runs, balls, wk = int(df["runs"].sum()), int(df["balls"].sum()), int(df["wickets"].sum())
    return {"wickets": wk,
            "economy": round(runs / (balls / 6), 2) if balls else None,
            "wkts_per_inn": round(wk / innings, 2) if innings else None}


def _bowl_window(bowl, pick):
    r = bowl["wickets"].rolling(WINDOW).sum()
    if r.notna().sum() == 0:
        return None
    i = int(r.idxmax() if pick == "best" else r.idxmin())
    w = bowl.iloc[i - WINDOW + 1: i + 1]
    return {"from": str(w["date"].iloc[0].date()), "to": str(w["date"].iloc[-1].date()),
            "innings": len(w), **_bowl_agg(w, len(w))}


def _bowl_trend(q):
    if len(q) < 4:
        return None
    slope = float(np.polyfit(q["year"].astype(float), q["economy"].astype(float), 1)[0])
    recent, earlier = q.tail(3), q.iloc[:-3]
    r = _bowl_agg(recent, int(recent["innings"].sum()))
    e = _bowl_agg(earlier, int(earlier["innings"].sum()))
    raw = round(r["economy"] - e["economy"], 2)
    league = round(_league_econ(recent["year"]) - _league_econ(earlier["year"]), 2)
    rel = round(raw - league, 2)
    label = lambda v: "improved" if v <= -0.3 else ("worse" if v >= 0.3 else "steady")
    return {"economy_slope_per_year": round(slope, 2), "recent_years": recent["year"].astype(int).tolist(),
            "recent": r, "earlier": e, "economy_change": raw, "league_economy_change": league,
            "relative_change": rel, "direction": label(rel), "direction_raw": label(raw)}


# ---------------------------------------------------------------- the function
def get_career_trends(player):
    who = _who(player)
    if who["status"] != "ok":
        return _not_found(who)
    name = who["player"]
    data = {"player": name, "player_id": who["player_id"], "window_innings": WINDOW}
    sample, warnings, chart = {}, [], {}

    # ---------------- batting
    bat = table("player_match_batting")
    bat = bat[bat["batter"] == name].sort_values("inning_no").reset_index(drop=True)
    if len(bat):
        s = table("player_season_batting")
        s = s[s["batter"] == name].sort_values("year")
        bat["contrib"] = (bat["runs"] >= 20) | ((bat["runs"] >= 10) & (bat["strike_rate"] >= 150))
        cr = bat.groupby("year")["contrib"].mean().rename("contrib_rate").reset_index()
        s = s.merge(cr, on="year", how="left")
        q = s[s["innings"] >= MIN_INN]
        last = bat.tail(WINDOW)
        career, recent = _bat_agg(bat), _bat_agg(last)
        d = {
            "seasons": _rows(s, ["year", "team", "innings", "runs", "avg", "sr", "runs_per_inn", "contrib_rate"]),
            "teams": _team_spans(s),
            "events": _events(q, "runs_per_inn", "runs per innings"),
            "best_window": _bat_window(bat, "best"),
            "worst_window": _bat_window(bat, "worst"),
            "recent_form": {"from": str(last["date"].iloc[0].date()), "to": str(last["date"].iloc[-1].date()),
                            "innings": len(last), **recent,
                            "career_avg": career["avg"], "career_sr": career["sr"]},
            "trend": _bat_trend(q),
        }
        data["batting"] = d
        sample["batting_innings"], sample["batting_seasons"] = len(bat), len(s)
        chart["batting"] = {
            "seasons": {"x": s["year"].astype(int).tolist(), "runs": s["runs"].astype(int).tolist(),
                        "avg": [_native(v) for v in s["avg"]], "sr": [_native(v) for v in s["sr"]]},
            "rolling": {"x": bat["inning_no"].astype(int).tolist(),
                        "date": [str(t.date()) for t in bat["date"]],
                        "roll_avg": [_native(v) for v in bat["roll_avg"]],
                        "roll_sr": [_native(v) for v in bat["roll_sr"]]},
        }
        if d["events"] is None:
            warnings.append(f"fewer than 3 seasons with {MIN_INN}+ batting innings: peaks and slumps not computed")

    # ---------------- bowling (only for players who have bowled at least 20 overs)
    bowl = table("player_match_bowling")
    bowl = bowl[bowl["bowler"] == name].sort_values("inning_no").reset_index(drop=True)
    if len(bowl) and bowl["balls"].sum() >= 120:
        b = table("player_season_bowling")
        b = b[b["bowler"] == name].sort_values("year").copy()
        b["wkts_per_inn"] = b["wickets"] / b["innings"]
        q = b[b["innings"] >= MIN_INN]
        last = bowl.tail(WINDOW)
        rr = bowl["runs"].rolling(WINDOW, min_periods=5).sum()
        rb = bowl["balls"].rolling(WINDOW, min_periods=5).sum()
        roll_econ = rr / rb.where(rb > 0) * 6
        d = {
            "seasons": _rows(b, ["year", "team", "innings", "balls", "runs", "wickets", "economy",
                                 "avg", "sr", "wkts_per_inn"]),
            "teams": _team_spans(b),
            "events": _events(q, "wkts_per_inn", "wickets per innings"),
            "economy_extremes": ({"best": {"year": int(q.loc[q["economy"].idxmin(), "year"]),
                                           "economy": round(float(q["economy"].min()), 2)},
                                  "worst": {"year": int(q.loc[q["economy"].idxmax(), "year"]),
                                            "economy": round(float(q["economy"].max()), 2)}}
                                 if len(q) else None),
            "best_window": _bowl_window(bowl, "best"),
            "worst_window": _bowl_window(bowl, "worst"),
            "recent_form": {"from": str(last["date"].iloc[0].date()), "to": str(last["date"].iloc[-1].date()),
                            "innings": len(last), **_bowl_agg(last, len(last)),
                            "career_economy": _bowl_agg(bowl, len(bowl))["economy"]},
            "trend": _bowl_trend(q),
        }
        data["bowling"] = d
        sample["bowling_innings"], sample["bowling_seasons"] = len(bowl), len(b)
        chart["bowling"] = {
            "seasons": {"x": b["year"].astype(int).tolist(), "wickets": b["wickets"].astype(int).tolist(),
                        "economy": [_native(v) for v in b["economy"]]},
            "rolling": {"x": bowl["inning_no"].astype(int).tolist(),
                        "date": [str(t.date()) for t in bowl["date"]],
                        "roll_economy": [_native(v) for v in roll_econ]},
        }
        if d["events"] is None:
            warnings.append(f"fewer than 3 seasons with {MIN_INN}+ bowling innings: peaks and slumps not computed")

    if not sample:
        return failure("No IPL data for this player.")
    return success(data, sample, warnings, chart)

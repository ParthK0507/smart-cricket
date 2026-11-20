import pandas as pd

from core.compare import compare_players
from core.data import table
from core.home_away import get_home_away_stats
from core.leaderboard import get_leaderboard
from core.live import predict_live
from core.matchup import get_bowler_matchup
from core.opposition import get_opposition_stats
from core.player import _rows, _who, get_career_stats, get_phase_stats, get_season_stats
from core.predict import predict_chase
from core.preview import get_match_preview
from core.result import failure, success
from core.trends import get_career_trends
from core.venue_stats import get_venue_stats

PHASES = ["powerplay", "middle", "death"]


def _fail(agent, message):
    return {"agent": agent, "ok": False, "results": {}, "insights": [], "warnings": [], "charts": {},
            "errors": [message], "candidates": []}


def _pack(agent, results, insights=None):
    """Bundle engine results. ok when at least one succeeded; failures are kept as errors."""
    warnings, charts, errors, candidates = [], {}, [], []
    for label, r in results.items():
        if r["ok"]:
            warnings += [f"{label}: {w}" for w in r["warnings"]]
            if r.get("chart"):
                charts[label] = r["chart"]
        else:
            errors.append(f"{label}: {r['error']}")
            candidates = candidates or r.get("candidates", [])
    return {"agent": agent, "ok": any(r["ok"] for r in results.values()), "results": results,
            "insights": insights or [], "warnings": warnings, "charts": charts, "errors": errors,
            "candidates": candidates}


def _insights(name, role, year=None):
    """Strengths and weaknesses, each backed by numbers: a phase rate against the league's in the same seasons."""
    out = []
    if role in ("batter", "all-rounder"):
        t = table("batting_by_phase")
        lg = t.groupby(["year", "phase"])[["runs", "balls"]].sum()
        lg["rate"] = lg["runs"] / lg["balls"] * 100
        p = t[t["batter"] == name]
        if year is not None:
            p = p[p["year"] == year]
        for ph in PHASES:
            pp = p[p["phase"] == ph]
            balls = int(pp["balls"].sum())
            if balls < 150:
                continue
            idx = pd.MultiIndex.from_arrays([pp["year"], pp["phase"]])
            exp = float((lg["rate"].reindex(idx).values * pp["balls"].values).sum() / balls)
            act = float(pp["runs"].sum() / balls * 100)
            if abs(act - exp) >= 8:
                out.append({"kind": "strength" if act > exp else "weakness", "area": f"batting, {ph}",
                            "text": f"{ph} strike rate {act:.0f} against {exp:.0f} for the league in the same "
                                    f"seasons ({act - exp:+.0f}), over {balls} balls"})
    if role in ("bowler", "all-rounder"):
        t = table("bowling_by_phase")
        lg = t.groupby(["year", "phase"])[["runs", "balls"]].sum()
        lg["rate"] = lg["runs"] / (lg["balls"] / 6)
        p = t[t["bowler"] == name]
        if year is not None:
            p = p[p["year"] == year]
        for ph in PHASES:
            pp = p[p["phase"] == ph]
            balls = int(pp["balls"].sum())
            if balls < 180:
                continue
            idx = pd.MultiIndex.from_arrays([pp["year"], pp["phase"]])
            exp = float((lg["rate"].reindex(idx).values * pp["balls"].values).sum() / balls)
            act = float(pp["runs"].sum() / (balls / 6))
            if abs(act - exp) >= 0.4:
                out.append({"kind": "strength" if act < exp else "weakness", "area": f"bowling, {ph}",
                            "text": f"{ph} economy {act:.2f} against {exp:.2f} for the league in the same "
                                    f"seasons ({act - exp:+.2f}), over {balls} balls"})
    return out


def _all_opponents(player):
    w = _who(player)
    if w["status"] != "ok":
        msg = "Which player do you mean?" if w["status"] == "ambiguous" else "Player not found."
        return failure(msg, w["candidates"])
    name = w["player"]
    data = {"player": name, "player_id": w["player_id"]}
    bat = table("batter_vs_team")
    bat = bat[bat["batter"] == name].sort_values("runs", ascending=False)
    if len(bat):
        data["batting"] = _rows(bat, ["opposition", "innings", "runs", "balls", "outs", "avg", "sr", "high_score"])
    bowl = table("player_match_bowling")
    bowl = bowl[bowl["bowler"] == name]
    if len(bowl):
        g = (bowl.groupby("opposition").agg(innings=("balls", "size"), balls=("balls", "sum"),
                                            runs=("runs", "sum"), wickets=("wickets", "sum")).reset_index())
        g["economy"] = g["runs"] / (g["balls"].where(g["balls"] > 0) / 6)
        data["bowling"] = _rows(g.sort_values("wickets", ascending=False),
                                ["opposition", "innings", "balls", "runs", "wickets", "economy"])
    if "batting" not in data and "bowling" not in data:
        return failure("No IPL data for this player.")
    return success(data, {"opponents": len(data.get("batting", data.get("bowling")))})


# ---------------------------------------------------------------- Agent 1
def player_analyst(player, year=None):
    c = get_career_stats(player)
    res = {"career": c}
    insights = []
    if c["ok"]:
        res["seasons"] = get_season_stats(player)
        res["phases"] = get_phase_stats(player, year)
        insights = _insights(c["data"]["player"], c["data"]["role"], year)
    return _pack("player_analyst", res, insights)


# ---------------------------------------------------------------- Agent 2
def player_comparator(players, role="auto"):
    sc = compare_players(players, role)
    res = {"scorecard": sc}
    if sc["ok"]:
        for n in sc["data"]["players"]:
            res[f"seasons: {n}"] = get_season_stats(n)
    return _pack("player_comparator", res)


# ---------------------------------------------------------------- Agent 3
def opposition_analyst(player, team=None):
    if team:
        return _pack("opposition_analyst", {"opposition": get_opposition_stats(player, team)})
    return _pack("opposition_analyst", {"all_opponents": _all_opponents(player)})


# ---------------------------------------------------------------- Agent 4
def matchup_analyst(batter, bowler):
    return _pack("matchup_analyst", {"matchup": get_bowler_matchup(batter, bowler)})


# ---------------------------------------------------------------- Agent 5
def trend_analyst(player):
    return _pack("trend_analyst", {"trends": get_career_trends(player)})


# ---------------------------------------------------------------- Agent 6
def venue_analyst(player, venues=None):
    res = {f"venue: {v}": get_venue_stats(player, v) for v in (venues or [])}
    res["home_away"] = get_home_away_stats(player)
    return _pack("venue_analyst", res)


# ---------------------------------------------------------------- Agent 7 (predictors)
def match_predictor(mode="preview", team1=None, team2=None, venue=None, batting_first=None, chasing=None,
                    first_innings_runs=None, runs=None, wickets=None, balls_bowled=None):
    if mode == "preview":
        return _pack("match_predictor", {"preview": get_match_preview(team1, team2, venue)})
    if mode == "chase":
        return _pack("match_predictor", {"chase": predict_chase(batting_first, chasing, venue, first_innings_runs)})
    if mode == "live":
        return _pack("match_predictor", {"live": predict_live(batting_first, chasing, venue, first_innings_runs,
                                                              runs, wickets, balls_bowled)})
    return _fail("match_predictor", "mode must be 'preview', 'chase' or 'live'")


# ---------------------------------------------------------------- Agent 8 (rankings)
def leaderboard_analyst(metric, role="batting", top=10, **filters):
    return _pack("leaderboard_analyst", {"ranking": get_leaderboard(metric, role=role, top=top, **filters)})


AGENTS = {"player_analyst": player_analyst, "player_comparator": player_comparator,
          "opposition_analyst": opposition_analyst, "matchup_analyst": matchup_analyst,
          "trend_analyst": trend_analyst, "venue_analyst": venue_analyst,
          "match_predictor": match_predictor, "leaderboard_analyst": leaderboard_analyst}


def run_agent(name, args):
    """Run one agent; whatever happens, the caller gets a result dict back and never an exception."""
    fn = AGENTS.get(name)
    if fn is None:
        return _fail(name, f"unknown agent '{name}'")
    try:
        return fn(**args)
    except Exception as e:
        return _fail(name, f"{type(e).__name__}: {e}")

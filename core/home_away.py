import json
from functools import lru_cache

from core.config import ROOT
from core.data import table
from core.player import _who, _not_found
from core.result import success, failure, small_sample

CONFIG = ROOT / "config" / "home_grounds.json"
SIDES = ["home", "away", "neutral"]


@lru_cache(maxsize=1)
def _config():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    home = {(team, int(y), venue) for team, venues in cfg["home"].items()
            for venue, years in venues.items() for y in years}
    return {"neutral_years": set(cfg["neutral_years"]), "uae_year": cfg["uae_neutral_year"],
            "uae_venues": set(cfg["uae_venues"]), "home": home}


def venue_context(team, opposition, year, venue):
    """'home', 'away' or 'neutral' for `team` in a match against `opposition`."""
    c = _config()
    year = int(year)
    if year in c["neutral_years"] or (year == c["uae_year"] and venue in c["uae_venues"]):
        return "neutral"
    mine = (team, year, venue) in c["home"]
    theirs = (opposition, year, venue) in c["home"]
    if mine and not theirs:
        return "home"
    if theirs and not mine:
        return "away"
    return "neutral"


def _label(df, team_col):
    df = df.copy()
    df["side"] = [venue_context(t, o, y, v) for t, o, y, v in
                  zip(df[team_col], df["opposition"], df["year"], df["venue"])]
    return df


def _bat_block(df):
    runs, balls, outs, n = int(df["runs"].sum()), int(df["balls"].sum()), int(df["outs"].sum()), len(df)
    return {"innings": n, "runs": runs, "balls": balls, "outs": outs,
            "avg": round(runs / outs, 2) if outs else None,
            "sr": round(runs / balls * 100, 2) if balls else None,
            "high_score": int(df["runs"].max()) if n else None,
            "fifties": int(((df["runs"] >= 50) & (df["runs"] < 100)).sum()),
            "hundreds": int((df["runs"] >= 100).sum())}


def _bowl_block(df):
    balls, runs, wk, n = int(df["balls"].sum()), int(df["runs"].sum()), int(df["wickets"].sum()), len(df)
    best = df.sort_values(["wickets", "runs"], ascending=[False, True]).iloc[0] if n else None
    return {"innings": n, "balls": balls, "runs": runs, "wickets": wk,
            "economy": round(runs / (balls / 6), 2) if balls else None,
            "avg": round(runs / wk, 2) if wk else None,
            "sr": round(balls / wk, 2) if wk else None,
            "best_figures": f"{int(best['wickets'])}/{int(best['runs'])}" if best is not None else None}


def _gap(block, key):
    h, a = block["home"][key], block["away"][key]
    return round(h - a, 2) if h is not None and a is not None else None


def get_home_away_stats(player):
    who = _who(player)
    if who["status"] != "ok":
        return _not_found(who)
    name = who["player"]
    data = {"player": name, "player_id": who["player_id"]}
    sample, warnings, chart = {}, [], {}

    bat = table("player_match_batting")
    bat = bat[bat["batter"] == name]
    if len(bat):
        bat = _label(bat, "batting_team")
        block = {s: _bat_block(bat[bat["side"] == s]) for s in SIDES}
        data["batting"] = block
        data["batting_home_minus_away"] = {"avg": _gap(block, "avg"), "sr": _gap(block, "sr")}
        sample["batting_innings"] = len(bat)
        chart["batting"] = {"x": [s.capitalize() for s in SIDES],
                            "avg": [block[s]["avg"] for s in SIDES], "sr": [block[s]["sr"] for s in SIDES]}
        for s in ("home", "away"):
            w = small_sample(block[s]["innings"], 10, f"{s} batting innings")
            if w:
                warnings.append(w)

    bowl = table("player_match_bowling")
    bowl = bowl[bowl["bowler"] == name]
    if len(bowl) and bowl["balls"].sum() >= 120:
        bowl = _label(bowl, "team")
        block = {s: _bowl_block(bowl[bowl["side"] == s]) for s in SIDES}
        data["bowling"] = block
        data["bowling_home_minus_away"] = {"economy": _gap(block, "economy"), "avg": _gap(block, "avg")}
        sample["bowling_innings"] = len(bowl)
        chart["bowling"] = {"x": [s.capitalize() for s in SIDES],
                            "economy": [block[s]["economy"] for s in SIDES],
                            "wickets": [block[s]["wickets"] for s in SIDES]}
        for s in ("home", "away"):
            w = small_sample(block[s]["innings"], 10, f"{s} bowling innings")
            if w:
                warnings.append(w)

    if not sample:
        return failure("No IPL data for this player.")
    return success(data, sample, warnings, chart)

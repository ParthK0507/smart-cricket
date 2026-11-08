from functools import lru_cache

import numpy as np
import pandas as pd

from core.data import table
from core.home_away import venue_context
from core.predict import _par_at, _team_or_error
from core.result import success, failure
from core.venues import resolve_venue


def _pct(x):
    return None if x is None or pd.isna(x) else round(float(x) * 100, 1)


@lru_cache(maxsize=1)
def _matches():
    m = table("matches")
    m = m[m["final_winner"].notna()].copy()
    first = (table("balls").query("innings == 1").groupby("match_id")
             .agg(bat_first=("batting_team", "first"), first_runs=("runs_total", "sum")).reset_index())
    d = m.merge(first, on="match_id")
    d["chasing"] = np.where(d["bat_first"] == d["team1"], d["team2"], d["team1"])
    d["chase_win"] = (d["final_winner"] != d["bat_first"]).astype(int)
    d["rain"] = d["method"].notna()
    return d.sort_values("match_seq").reset_index(drop=True)


def _ground_block(d, ground, par):
    g = d[d["venue"] == ground]

    def block(x):
        dry = x[~x["rain"]]
        return {"matches": len(x),
                "chase_win_pct": _pct(x["chase_win"].mean()) if len(x) else None,
                "avg_first_innings": round(float(dry["first_runs"].mean()), 1) if len(dry) else None}

    dry = g[~g["rain"]]
    out = block(g)
    chase = out["chase_win_pct"]
    out.update({
        "par_score": round(par, 1),
        "bat_first_win_pct": None if chase is None else round(100 - chase, 1),
        "highest_first_innings": int(dry["first_runs"].max()) if len(dry) else None,
        "lowest_first_innings": int(dry["first_runs"].min()) if len(dry) else None,
        "toss_field_pct": _pct((g["toss_decision"] == "field").mean()) if len(g) else None,
        "toss_winner_won_pct": _pct((g["toss_winner"] == g["final_winner"]).mean()) if len(g) else None,
        "since_2022": block(g[g["year"] >= 2022]),
    })
    return out


def _h2h(d, t1, t2):
    h = d[((d["team1"] == t1) & (d["team2"] == t2)) | ((d["team1"] == t2) & (d["team2"] == t1))]
    rec = h[h["year"] >= 2020]
    wins = lambda x: {t1: int((x["final_winner"] == t1).sum()), t2: int((x["final_winner"] == t2).sum())}
    return {"meetings": len(h), "wins": wins(h),
            "since_2020": {"meetings": len(rec), "wins": wins(rec)},
            "last_meetings": [{"date": str(r.date.date()), "venue": r.venue, "winner": r.final_winner}
                              for r in h.tail(5).itertuples()]}


def _team_block(d, team, other, ground, latest):
    tm = d[(d["team1"] == team) | (d["team2"] == team)]
    tg = tm[tm["venue"] == ground]
    last15 = tm.tail(15)
    return {"team": team, "matches": len(tm), "last_played": int(tm["year"].max()),
            "form_last5": "".join("W" if w == team else "L" for w in tm.tail(5)["final_winner"]),
            "wins_last15": int((last15["final_winner"] == team).sum()), "of_last15": len(last15),
            "at_ground": {"matches": len(tg), "wins": int((tg["final_winner"] == team).sum()),
                          "win_pct": _pct((tg["final_winner"] == team).mean()) if len(tg) else None},
            "ground_status_latest_season": venue_context(team, other, latest, ground)}


def get_match_preview(team1, team2, venue):
    t1, err = _team_or_error(team1, "team 1")
    if err:
        return err
    t2, err = _team_or_error(team2, "team 2")
    if err:
        return err
    if t1 == t2:
        return failure("The two teams must be different.")
    v = resolve_venue(venue)
    if v["status"] != "ok":
        msg = "Which ground do you mean?" if v["status"] == "ambiguous" else "Ground not found."
        return failure(msg, [{"venue": c} for c in v["candidates"]])
    ground = v["venue"]

    d = _matches()
    latest = int(d["year"].max())
    par, _ = _par_at(ground)
    g, h = _ground_block(d, ground, par), _h2h(d, t1, t2)
    teams = [_team_block(d, t, o, ground, latest) for t, o in ((t1, t2), (t2, t1))]

    warnings, highlights = [], []
    if g["matches"] < 10:
        warnings.append(f"only {g['matches']} IPL matches at this ground, so the ground figures are thin")
    if h["meetings"] == 0:
        warnings.append("these teams have never met in the IPL")
    elif h["meetings"] < 5:
        warnings.append(f"only {h['meetings']} previous meetings")
    for t in teams:
        if t["last_played"] < latest:
            warnings.append(f"{t['team']} last played in {t['last_played']}")
        if t["at_ground"]["matches"] < 5:
            warnings.append(f"{t['team']} has played only {t['at_ground']['matches']} match(es) at this ground")

    overall = float(d["chase_win"].mean() * 100)
    if g["matches"] >= 20 and abs(g["chase_win_pct"] - overall) >= 5:
        highlights.append(f"Chasing teams have won {g['chase_win_pct']}% of {g['matches']} matches here, "
                          f"against {overall:.1f}% across all IPL matches.")
    if h["meetings"] >= 8:
        lead = max(h["wins"], key=h["wins"].get)
        if h["wins"][lead] / h["meetings"] >= 0.65:
            highlights.append(f"{lead} has won {h['wins'][lead]} of {h['meetings']} meetings.")
    if g["since_2022"]["matches"] >= 8 and g["avg_first_innings"] and g["since_2022"]["avg_first_innings"]:
        diff = g["since_2022"]["avg_first_innings"] - g["avg_first_innings"]
        if abs(diff) >= 5:
            highlights.append(f"First-innings scores here since 2022 average {g['since_2022']['avg_first_innings']}, "
                              f"{abs(diff):.0f} runs {'above' if diff > 0 else 'below'} the all-time average.")

    dry = d[(d["venue"] == ground) & ~d["rain"]]
    by = dry.groupby("year")["first_runs"].agg(["mean", "size"])
    chart = {"x": [int(y) for y in by.index], "avg_first": [round(float(x), 1) for x in by["mean"]],
             "matches": [int(n) for n in by["size"]], "par": round(par, 1)}
    data = {"team1": t1, "team2": t2, "venue": ground, "as_of": str(d["date"].max().date()),
            "ground": g, "head_to_head": h, "teams": teams, "highlights": highlights}
    return success(data, {"ground_matches": g["matches"], "meetings": h["meetings"]}, warnings, chart)

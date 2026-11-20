"""The Critic: re-checks every analyst result with code before any text is written. Fails closed."""
import json

from core.data import table

TOP_FACT_CHARS = 20000
DROP = {"player_id", "player_ids"}


def _sum(rows, key):
    return sum(r[key] for r in rows)


def _rows(x):
    return list(x.values()) if isinstance(x, dict) else list(x)


def _career(name, side):
    t = table("career_batting" if side == "batting" else "career_bowling")
    row = t[t["batter" if side == "batting" else "bowler"] == name]
    return None if row.empty else row.iloc[0]


def _split_checks(d, label):
    """By-year and by-phase tables must add back to their totals (opposition and venue results)."""
    out = []
    for side, key in (("batting", "runs"), ("bowling", "wickets")):
        b = d.get(side)
        if b:
            out.append((f"{label}: {side} by-year totals add up", _sum(b["by_year"], key) == b[key]))
            out.append((f"{label}: {side} by-phase totals add up", _sum(_rows(b["by_phase"]), key) == b[key]))
    return out


def _check_player(res):
    r, out = res["results"], []
    c, s, p = r.get("career"), r.get("seasons"), r.get("phases")
    if not (c and c["ok"]):
        return out
    cd = c["data"]
    if s and s["ok"]:
        for side, key in (("batting", "runs"), ("bowling", "wickets")):
            if side in cd and side in s["data"]:
                out.append((f"season {key} add up to career {key}", _sum(s["data"][side], key) == cd[side][key]))
                out.append((f"season innings add up ({side})", _sum(s["data"][side], "innings") == cd[side]["innings"]))
    if p and p["ok"] and p["data"].get("year") is None:
        pdata = p["data"]
        if "batting" in cd and "batting" in pdata:
            for key in ("runs", "balls", "outs"):
                out.append((f"batting phase {key} add up to career", _sum(_rows(pdata["batting"]), key) == cd["batting"][key]))
        if "bowling" in cd and "bowling" in pdata:
            for key in ("balls", "wickets"):
                out.append((f"bowling phase {key} add up to career", _sum(_rows(pdata["bowling"]), key) == cd["bowling"][key]))
    return out


def _check_compare(res):
    r = res["results"]
    sc = r.get("scorecard")
    if not (sc and sc["ok"]):
        return []
    d = sc["data"]
    names = set(d["players"])
    out = [("wins plus ties equal the scored metrics", sum(d["wins"].values()) + d["ties"] == d["scored_metrics"]),
           ("every metric has a leader among the players, or a tie",
            all(m["winner"] in names | {"tie", "n/a"} for m in d["metrics"].values())),
           ("every player has a value for each metric", all(all(n in m["values"] for n in names) for m in d["metrics"].values()))]
    ok = True
    for m in d["metrics"].values():
        if m["winner"] in names:
            v = m["values"]
            ok = ok and v[m["winner"]] == (max(v.values()) if m["higher_is_better"] else min(v.values()))
    out.append(("each leader has the best value", ok))
    side, key = ("batting", "runs") if d["role"] == "batting" else ("bowling", "wickets")
    for n in d["players"]:
        s = r.get(f"seasons: {n}")
        if s and s["ok"] and side in s["data"] and key in d["context"]:
            out.append((f"season {key} add up to the scorecard for {n}", _sum(s["data"][side], key) == d["context"][key][n]))
    return out


def _check_matchup(res):
    r = res["results"].get("matchup")
    if not (r and r["ok"]):
        return []
    d, out = r["data"], []
    for name, rows in (("by_year", d["by_year"]), ("by_phase", d["by_phase"])):
        out.append((f"matchup {name} totals add up",
                    all(_sum(rows, k) == d[t] for k, t in (("runs", "runs"), ("balls", "balls"), ("outs", "dismissals")))))
    h = table("batter_vs_bowler")
    row = h[(h["batter"] == d["batter"]) & (h["bowler"] == d["bowler"])]
    out.append(("matchup matches the batter-vs-bowler table",
                (not row.empty) and (int(row.iloc[0]["runs"]), int(row.iloc[0]["balls"]), int(row.iloc[0]["outs"]))
                == (d["runs"], d["balls"], d["dismissals"])))
    return out


def _check_opposition(res):
    r, out = res["results"], []
    o = r.get("opposition")
    if o and o["ok"]:
        out += _split_checks(o["data"], "opposition")
    a = r.get("all_opponents")
    if a and a["ok"]:
        d = a["data"]
        for side, key in (("batting", "runs"), ("bowling", "wickets")):
            if side in d:
                row = _career(d["player"], side)
                if row is not None:
                    out.append((f"all opponents: {side} {key} add up to the career", _sum(d[side], key) == int(row[key])))
    return out


def _check_trend(res):
    r = res["results"].get("trends")
    if not (r and r["ok"]):
        return []
    d, out = r["data"], []
    chart = res["charts"].get("trends", {})
    for side, key in (("batting", "runs"), ("bowling", "wickets")):
        b = d.get(side)
        row = _career(d["player"], side) if b else None
        if row is None:
            continue
        out.append((f"trend: season {key} add up to the career", _sum(b["seasons"], key) == int(row[key])))
        out.append((f"trend: season innings add up ({side})", _sum(b["seasons"], "innings") == int(row["innings"])))
        n = len(chart.get(side, {}).get("rolling", {}).get("x", []))
        if n:
            out.append((f"trend: the form line has one point per innings ({side})", n == int(row["innings"])))
    return out


def _check_venue(res):
    r, out = res["results"], []
    for label, x in r.items():
        if label.startswith("venue:") and x["ok"]:
            out += _split_checks(x["data"], label)
    ha = r.get("home_away")
    if ha and ha["ok"]:
        d = ha["data"]
        for side in ("batting", "bowling"):
            if side in d:
                row = _career(d["player"], side)
                if row is not None:
                    out.append((f"home, away and neutral innings add up to the career ({side})",
                                sum(v["innings"] for v in d[side].values()) == int(row["innings"])))
    return out


def _check_predictor(res):
    r, out = res["results"], []
    for label in ("chase", "live"):
        x = r.get(label)
        if x and x["ok"]:
            d = x["data"]
            p = d["chase_win_prob"]
            out.append(("probabilities are between 0 and 1", 0 <= p <= 1))
            out.append(("probabilities add to 1", abs(p + d["bat_first_win_prob"] - 1) < 0.0015))
            out.append(("the favourite has the higher probability", abs(p - 0.5) < 0.001 or ((d["favourite"] == d["chasing"]) == (p >= 0.5))))
    x = r.get("preview")
    if x and x["ok"]:
        g, h = x["data"]["ground"], x["data"]["head_to_head"]
        out.append(("head-to-head wins add up to the meetings", sum(h["wins"].values()) == h["meetings"]))
        if g["chase_win_pct"] is not None:
            out.append(("chase and bat-first percentages add to 100", abs(g["chase_win_pct"] + g["bat_first_win_pct"] - 100) < 0.11))
    return out


def _check_leaderboard(res):
    x = res["results"].get("ranking")
    if not (x and x["ok"]):
        return []
    d = x["data"]
    rows = d["rows"]
    vals = [r["value"] for r in rows]
    return [("rows are sorted", vals == sorted(vals, reverse=d["higher_is_better"])),
            ("ranks run from 1", [r["rank"] for r in rows] == list(range(1, len(rows) + 1))),
            ("no player appears twice", len({r["player"] for r in rows}) == len(rows))]


CHECKS = {"player_analyst": _check_player, "player_comparator": _check_compare, "opposition_analyst": _check_opposition,
          "matchup_analyst": _check_matchup, "trend_analyst": _check_trend, "venue_analyst": _check_venue,
          "match_predictor": _check_predictor, "leaderboard_analyst": _check_leaderboard}


def _run(res):
    fn = CHECKS.get(res.get("agent"))
    if fn is None:
        return [("the agent is known", False)]
    try:
        return fn(res)
    except Exception as e:                      # fail closed: a check that cannot run counts as failed
        return [(f"the checks could run ({type(e).__name__})", False)]


# ------------------------------------------------------------------ the verified fact sheet
def _compact(obj, cap):
    if isinstance(obj, dict):
        return {k: _compact(v, cap) for k, v in obj.items() if k not in DROP}
    if isinstance(obj, list):
        return [_compact(v, cap) for v in obj[:cap]]
    if isinstance(obj, float):
        return None if obj != obj else round(obj, 2)
    return obj


def build_facts(res):
    for cap in (20, 8):
        facts = {"agent": res["agent"],
                 "data": {label: _compact(x["data"], cap) for label, x in res["results"].items() if x["ok"]},
                 "insights": [i["text"] for i in res.get("insights", [])]}
        if len(json.dumps(facts)) <= TOP_FACT_CHARS:
            break
    return facts


def _numbers(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _numbers(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _numbers(v)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        yield obj


def allowed_numbers(facts):
    """Every number the summarizer may quote: the fact sheet's numbers, rounded, and probabilities as percentages."""
    ok = set()
    for n in _numbers(facts):
        ok |= {float(n), round(float(n), 1), round(float(n), 2), float(round(n))}
        if 0 <= n <= 1:
            ok |= {round(n * 100, 1), float(round(n * 100))}
    return ok


def review(answer):
    """answer: the aggregate from the graph. Returns what was verified, what failed and what the summarizer may see."""
    verified, failed, flags, errors, ran, seen = [], [], [], [], 0, set()
    for res in (answer or {}).get("results", []):
        if not res.get("ok"):
            errors += res.get("errors", [])
            continue
        checks = _run(res)
        ran += len(checks)
        bad = [n for n, ok in checks if not ok]
        if bad:
            failed.append({"agent": res["agent"], "index": res.get("index"), "checks": bad})
            continue
        verified.append(res)
        for w in res.get("warnings", []):
            if w not in seen:
                seen.add(w)
                flags.append(w)
    return {"ok": bool(verified), "verified_agents": [r["agent"] for r in verified], "failed": failed,
            "errors": errors, "flags": flags, "checks_run": ran, "facts": [build_facts(r) for r in verified],
            "insights": [i for r in verified for i in r.get("insights", [])]}

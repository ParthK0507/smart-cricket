"""Draw the verified results of the analysts inside the Ask page."""
import pandas as pd
import streamlit as st

from app.charts import bar_chart, ground_scores_chart, radar_chart, rolling_chart, season_chart, win_curve_chart

_n = {"i": 0}


def reset_keys():
    _n["i"] = 0


def _key(prefix):
    _n["i"] += 1
    return f"{prefix}_{_n['i']}"


def chart(fig):
    st.plotly_chart(fig, key=_key("pc"))


def table(df, index=False):
    st.dataframe(df, hide_index=not index, key=_key("df"))


def _fmt(v, digits=1):
    return "-" if v is None else f"{v:,.{digits}f}"


def _years(values):
    return ", ".join(map(str, values)) or "none"


def _metrics(items):
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        col.metric(label, "-" if value is None else value)


def _bat_row(b):
    _metrics([("Innings", b["innings"]), ("Runs", f'{b["runs"]:,}'), ("Average", _fmt(b["avg"], 2)),
              ("Strike rate", _fmt(b["sr"], 2)), ("High score", b["high_score"])])


def _bowl_row(w):
    _metrics([("Innings", w["innings"]), ("Wickets", w["wickets"]), ("Economy", _fmt(w["economy"], 2)),
              ("Average", _fmt(w["avg"], 2)), ("Best", w["best_figures"])])


def _insights(items):
    for i in items:
        st.write(("Strength: " if i["kind"] == "strength" else "Weakness: ") + i["text"])


def _player(res):
    r = res["results"]
    c = r["career"]["data"] if r.get("career") and r["career"]["ok"] else None
    if not c:
        return
    b, w, role = c.get("batting"), c.get("bowling"), c["role"]
    show_bat = bool(b) and role in ("batter", "all-rounder")
    show_bowl = bool(w) and role in ("bowler", "all-rounder")
    st.markdown(f'**{c["player"]}** ({role})')
    if show_bat:
        _bat_row(b)
    if show_bowl:
        _bowl_row(w)
    _insights(res["insights"])
    ch = res["charts"].get("seasons", {})
    if show_bat and "batting" in ch:
        chart(season_chart(ch["batting"], f'{c["player"]}: runs and strike rate by season'))
    if show_bowl and "bowling" in ch:
        chart(season_chart(ch["bowling"], f'{c["player"]}: wickets and economy by season', bar="wickets",
                           line="economy", bar_name="Wickets", line_name="Economy"))
    ph = r.get("phases")
    if ph and ph["ok"]:
        for side, shown in (("batting", show_bat), ("bowling", show_bowl)):
            if shown and side in ph["data"]:
                st.write(f"{side.title()} by phase")
                table(pd.DataFrame.from_dict(ph["data"][side], orient="index").round(2), index=True)


def _compare(res):
    sc = res["results"].get("scorecard")
    if not (sc and sc["ok"]):
        return
    d = sc["data"]
    names = d["players"]
    st.markdown("**Ahead on:** " + ", ".join(f"{n} {d['wins'][n]}" for n in names)
                + f" of {d['scored_metrics']} scored metrics ({d['ties']} tied)")
    st.caption("A scorecard, not a verdict: role, era and sample size all matter.")
    rows = [{"Metric": m["label"], **{n: m["values"][n] for n in names}, "Leader": m["winner"]} for m in d["metrics"].values()]
    table(pd.DataFrame(rows).round(2))
    radar = (res["charts"].get("scorecard") or {}).get("radar")
    if radar:
        chart(radar_chart(radar, " vs ".join(names)))
    table(pd.DataFrame(d["context"]).astype(str), index=True)


def _matchup(res):
    x = res["results"].get("matchup")
    if not (x and x["ok"]):
        return
    d = x["data"]
    st.markdown(f'**{d["batter"]} against {d["bowler"]}**')
    _metrics([("Balls", d["balls"]), ("Runs", d["runs"]), ("Dismissals", d["dismissals"]),
              ("Strike rate", _fmt(d["strike_rate"], 2)), ("Dot balls %", _fmt(d["dot_pct"]))])
    st.caption(f'A rule-of-thumb verdict from strike rate and how often he is dismissed: {d["verdict"]}')
    ch = res["charts"].get("matchup")
    if ch:
        chart(season_chart(ch, "Runs and strike rate by season"))
    table(pd.DataFrame(d["by_phase"]).round(2))


def _split(d, chs, subject):
    """Layout shared by 'against a team' and 'at a ground'."""
    chs = chs or {}
    bat, bowl = d.get("batting"), d.get("bowling")
    if bat:
        st.markdown(f'**{d["player"]}: batting {subject}**')
        _bat_row(bat)
        st.caption(f'Career: average {_fmt(bat["career_avg"], 2)}, strike rate {_fmt(bat["career_sr"], 2)}')
        if "batting" in chs:
            chart(season_chart(chs["batting"], f"Runs and strike rate by season, {subject}"))
        table(pd.DataFrame.from_dict(bat["by_phase"], orient="index").round(2), index=True)
    if bowl:
        st.markdown(f'**{d["player"]}: bowling {subject}**')
        _bowl_row(bowl)
        st.caption(f'Career economy: {_fmt(bowl["career_economy"], 2)}')
        if "bowling" in chs:
            chart(season_chart(chs["bowling"], f"Wickets and economy by season, {subject}", bar="wickets",
                               line="economy", bar_name="Wickets", line_name="Economy"))
        table(pd.DataFrame.from_dict(bowl["by_phase"], orient="index").round(2), index=True)


def _opposition(res):
    r = res["results"]
    o = r.get("opposition")
    if o and o["ok"]:
        _split(o["data"], res["charts"].get("opposition"), f'against {o["data"]["opposition"]}')
    a = r.get("all_opponents")
    if a and a["ok"]:
        d = a["data"]
        st.markdown(f'**{d["player"]} against every team**')
        for side in ("batting", "bowling"):
            if side in d:
                st.write(side.title())
                table(pd.DataFrame(d[side]).round(2))


def _venue(res):
    for label, x in res["results"].items():
        if label.startswith("venue:") and x["ok"]:
            _split(x["data"], res["charts"].get(label), f'at {x["data"]["venue"]}')
    ha = res["results"].get("home_away")
    if ha and ha["ok"]:
        d = ha["data"]
        st.markdown(f'**{d["player"]}: home, away and neutral**')
        st.caption("Neutral covers 2009, 2020, 2021, the relocated 2022 season and the UAE leg of 2014.")
        for side in ("batting", "bowling"):
            if side in d:
                table(pd.DataFrame(d[side]).T.round(2), index=True)


def _trend(res):
    x = res["results"].get("trends")
    if not (x and x["ok"]):
        return
    d, ch = x["data"], res["charts"].get("trends", {})
    name = d["player"]
    st.markdown(f"**{name}: career ups and downs**")
    b, w = d.get("batting"), d.get("bowling")
    if b and sum(s["runs"] for s in b["seasons"]) >= 500:
        ev, tr = b["events"], b["trend"]
        if ev:
            st.write(f'Best season {ev["best_season"]["year"]} ({ev["best_season"]["value"]} runs per innings), worst '
                     f'{ev["worst_season"]["year"]} ({ev["worst_season"]["value"]}). Peak years: {_years(ev["peak_years"])}. '
                     f'Slump years: {_years(ev["slump_years"])}.')
        if tr:
            st.info(f'Strike rate in {_years(tr["recent_years"])}: {tr["recent"]["sr"]} against {tr["earlier"]["sr"]} before '
                    f'({tr["sr_change"]:+.1f}). The league moved {tr["league_sr_change"]:+.1f} over the same span, so '
                    f'measured against the league: {tr["direction"]}.')
        cb = ch.get("batting")
        if cb:
            chart(season_chart(cb["seasons"], f"{name}: runs and strike rate by season"))
            chart(rolling_chart(cb["rolling"], "roll_sr", f"{name}: strike rate over the last 10 innings", "Strike rate"))
    if w and sum(s["wickets"] for s in w["seasons"]) >= 30:
        ev, tr = w["events"], w["trend"]
        if ev:
            st.write(f'Best season {ev["best_season"]["year"]} ({ev["best_season"]["value"]} wickets per innings), worst '
                     f'{ev["worst_season"]["year"]} ({ev["worst_season"]["value"]}). Peak years: {_years(ev["peak_years"])}. '
                     f'Slump years: {_years(ev["slump_years"])}.')
        if tr:
            st.info(f'Economy in {_years(tr["recent_years"])}: {tr["recent"]["economy"]} against {tr["earlier"]["economy"]} before '
                    f'({tr["economy_change"]:+.2f}). The league moved {tr["league_economy_change"]:+.2f} over the same span, '
                    f'so measured against the league: {tr["direction"]}.')
        cw = ch.get("bowling")
        if cw:
            chart(season_chart(cw["seasons"], f"{name}: wickets and economy by season", bar="wickets", line="economy",
                               bar_name="Wickets", line_name="Economy"))
            chart(rolling_chart(cw["rolling"], "roll_economy", f"{name}: economy over the last 10 innings", "Economy"))


def _model_note(m):
    st.caption(f'A model estimate. Tested by walking forward season by season, it was right about '
               f'{m["accuracy"] * 100:.0f}% of the time (give or take {m["margin"] * 100:.1f} points). '
               "It uses the situation and the ground, not team names.")


def _predictor(res):
    r = res["results"]
    for mode in ("chase", "live"):
        x = r.get(mode)
        if x and x["ok"]:
            d = x["data"]
            st.markdown(f'**{d["chasing"]} chasing {d["first_innings_runs"]} at {d["venue"]}**')
            _metrics([(f'{d["chasing"]} win', f'{d["chase_win_prob"] * 100:.0f}%'),
                      (f'{d["batting_first"]} win', f'{d["bat_first_win_prob"] * 100:.0f}%'),
                      ("Par score", _fmt(d["par_score"]))])
            if d.get("model_used") == "live":
                st.write(f'{d["score"]} after {d["overs"]} overs: needs {d["runs_needed"]} from {d["balls_left"]} balls '
                         f'({d["required_rate"]} an over required, {d["current_rate"]} so far), {d["wickets_in_hand"]} wickets in hand.')
                if d.get("next_over"):
                    nxt = pd.DataFrame(d["next_over"]).pivot(index="next_over_runs", columns="wickets_in_over",
                                                              values="chase_win_prob") * 100
                    nxt.columns = ["no wicket" if k == 0 else "a wicket" for k in nxt.columns]
                    nxt.index.name = "runs in the next over"
                    st.write("What the next over could do to the chasing team's chances (%):")
                    table(nxt.round(0), index=True)
            elif d.get("live_note"):
                st.caption(d["live_note"])
            cv = res["charts"].get(mode)
            if cv and "x" in cv:
                chart(win_curve_chart(cv, "Chasing team win chance by first-innings score"))
            _model_note(d["model"])
    x = r.get("preview")
    if x and x["ok"]:
        d, g, h = x["data"], x["data"]["ground"], x["data"]["head_to_head"]
        st.markdown(f'**{d["team1"]} v {d["team2"]} at {d["venue"]}**')
        _metrics([("Matches here", g["matches"]), ("Par score", _fmt(g["par_score"])),
                  ("Chasing team won", f'{_fmt(g["chase_win_pct"])}%')])
        for hl in d["highlights"]:
            st.write(hl)
        st.write(f'Head to head: {d["team1"]} {h["wins"][d["team1"]]}, {d["team2"]} {h["wins"][d["team2"]]} '
                 f'in {h["meetings"]} meetings.')
        for t in d["teams"]:
            st.write(f'{t["team"]}: last 5 {t["form_last5"]}, {t["wins_last15"]} wins from the last {t["of_last15"]}.')
        cp = res["charts"].get("preview")
        if cp:
            chart(ground_scores_chart(cp, "Average first-innings score by season"))
        st.caption("Facts only: team ratings, home advantage and the toss added no measurable accuracy when tested.")


def _leaderboard(res):
    x = res["results"].get("ranking")
    if not (x and x["ok"]):
        return
    d = x["data"]
    st.markdown(f'**{d["label"]}: top {len(d["rows"])}**')
    if d["min_innings"] is not None:
        st.caption(f'Minimum {d["min_innings"]} innings to qualify. {d["qualified"]} players qualify.')
    cl = res["charts"].get("ranking")
    if cl:
        chart(bar_chart(cl["x"], cl["y"], d["label"], d["label"]))
    table(pd.DataFrame(d["rows"]).drop(columns=["player_id"], errors="ignore").round(2))


def _generic(res):
    st.write("No display is available for this result.")


RENDERERS = {"player_analyst": _player, "player_comparator": _compare, "opposition_analyst": _opposition,
             "matchup_analyst": _matchup, "trend_analyst": _trend, "venue_analyst": _venue,
             "match_predictor": _predictor, "leaderboard_analyst": _leaderboard}


def show_results(results):
    for i, res in enumerate(results):
        if i:
            st.divider()
        RENDERERS.get(res["agent"], _generic)(res)


def show(out):
    """Draw one answer from agents.service.answer()."""
    status = out["status"]
    if status == "answer":
        st.markdown(out["text"])
        if out.get("cached"):
            st.caption("Answered from an identical earlier question.")
        if out.get("source") == "rules":
            st.caption("This question was read with simple keyword rules.")
    elif status == "tables_only":
        st.info(out["message"])
    elif status == "clarify":
        st.info(out["message"])
        return
    elif status == "limited":
        st.warning(out["message"])
        return
    else:
        st.warning(out.get("message") or "I have no answer for that.")
        return
    if out.get("notice") and status == "answer":
        st.info(out["notice"])
    if out.get("failed"):
        st.warning("Part of the answer could not be verified, so it is left out: "
                   + ", ".join(sorted(set(out["failed"]))) + ".")
    if out.get("flags"):
        with st.expander("Notes and cautions"):
            for f in out["flags"]:
                st.write("- " + f)
    if out.get("results"):
        with st.expander("The numbers behind this answer", expanded=(status == "tables_only")):
            show_results(out["results"])

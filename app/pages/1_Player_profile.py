import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.charts import phase_chart, rolling_chart, season_chart
from core.config import DATA_THROUGH
from core.player import get_career_stats, get_phase_stats, get_season_stats
from core.resolve import resolve_player
from core.trends import get_career_trends

st.set_page_config(page_title="Player profile", page_icon="🏏", layout="wide")
st.title("Player profile")
st.caption(f"IPL data through {DATA_THROUGH}")


def metric_row(items):
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        col.metric(label, "-" if value is None else value)


def fmt(v, digits=1):
    return "-" if v is None else f"{v:,.{digits}f}"


query = st.text_input("Player name", value="Virat Kohli", help="Try: kohli, msd, bumrah, rashid khan")
res = resolve_player(query)
if res["status"] == "not_found":
    st.error("No player found. Check the spelling.")
    st.stop()
if res["status"] == "ambiguous":
    labels = {f'{c["player"]} ({c["years"]}, {c["team"]}, {c["matches"]} matches)': c["player_id"]
              for c in res["candidates"]}
    pid = labels[st.selectbox("Several players match. Which one?", list(labels))]
else:
    pid = res["player_id"]
    if res.get("match_type") == "dominant":
        st.caption(f'Showing {res["player"]}. Type the full name to pick a different player.')

career = get_career_stats(pid)
d = career["data"]
bat, bowl = d.get("batting"), d.get("bowling")
show_bat = bool(bat) and d["role"] in ("batter", "all-rounder")
show_bowl = bool(bowl) and d["role"] in ("bowler", "all-rounder")
info = bat or bowl

st.header(d["player"])
st.write(f'**{d["role"].title()}** | {info["first_year"]} to {info["last_year"]} | '
         f'{info["seasons"]} seasons | {info["teams"]}')
for w in career["warnings"]:
    if ("batting" in w and show_bat) or ("bowl" in w and show_bowl):
        st.warning(w)

trend_res = get_career_trends(pid)
trends, charts = trend_res["data"], trend_res["chart"]
seasons = get_season_stats(pid)["data"]
phases = get_phase_stats(pid)["data"]

tab_names = (["Batting"] if show_bat else []) + (["Bowling"] if show_bowl else [])
tabs = st.tabs(tab_names)


def years(values):
    return ", ".join(map(str, values)) or "none"


for name, tab in zip(tab_names, tabs):
    with tab:
        if name == "Batting":
            tb, cb = trends["batting"], charts["batting"]
            metric_row([("Innings", bat["innings"]), ("Runs", f'{bat["runs"]:,}'), ("Average", fmt(bat["avg"], 2)),
                        ("Strike rate", fmt(bat["sr"], 2)), ("High score", bat["high_score"]),
                        ("50s / 100s", f'{bat["fifties"]} / {bat["hundreds"]}'),
                        ("Consistency", fmt(bat["consistency"]))])
            ev, tr = tb["events"], tb["trend"]
            if ev:
                st.markdown(f'**Best season:** {ev["best_season"]["year"]} ({ev["best_season"]["value"]} runs per innings)'
                            f' | **Peak years:** {years(ev["peak_years"])} | **Slump years:** {years(ev["slump_years"])}')
            if tr:
                st.info(f'Strike rate in {years(tr["recent_years"])}: {tr["recent"]["sr"]} against {tr["earlier"]["sr"]} '
                        f'before ({tr["sr_change"]:+.1f}). The league moved {tr["league_sr_change"]:+.1f} over the '
                        f'same span, so measured against the league he is: {tr["direction"]}.')
            st.plotly_chart(season_chart(cb["seasons"], f'{d["player"]}: runs and strike rate by season'))
            st.plotly_chart(rolling_chart(cb["rolling"], "roll_sr",
                                          f'{d["player"]}: strike rate over the last 10 innings', "Strike rate"))
            choice = st.radio("Phase metric", ["Strike rate", "Average"], horizontal=True, key="bat_phase")
            key, label = ("sr", "Strike rate") if choice == "Strike rate" else ("avg", "Average")
            st.plotly_chart(phase_chart(phases["batting"], key, f'{d["player"]}: {label.lower()} by phase', label))
            df = pd.DataFrame(seasons["batting"])
            st.dataframe(df.round(2), hide_index=True)
        else:
            tb, cb = trends["bowling"], charts["bowling"]
            metric_row([("Innings", bowl["innings"]), ("Wickets", bowl["wickets"]), ("Economy", fmt(bowl["economy"], 2)),
                        ("Average", fmt(bowl["avg"], 2)), ("Strike rate", fmt(bowl["sr"], 1)),
                        ("Best", bowl["best_figures"]), ("3W / 5W", f'{bowl["three_w"]} / {bowl["five_w"]}'),
                        ("Consistency", fmt(bowl["consistency"]))])
            ev, tr = tb["events"], tb["trend"]
            if ev:
                st.markdown(f'**Best season:** {ev["best_season"]["year"]} ({ev["best_season"]["value"]} wickets per innings)'
                            f' | **Peak years:** {years(ev["peak_years"])} | **Slump years:** {years(ev["slump_years"])}')
            if tr:
                st.info(f'Economy in {years(tr["recent_years"])}: {tr["recent"]["economy"]} against {tr["earlier"]["economy"]} '
                        f'before ({tr["economy_change"]:+.2f}). The league moved {tr["league_economy_change"]:+.2f} over '
                        f'the same span, so measured against the league he is: {tr["direction"]}.')
            st.plotly_chart(season_chart(cb["seasons"], f'{d["player"]}: wickets and economy by season', bar="wickets",
                                         line="economy", bar_name="Wickets", line_name="Economy"))
            st.plotly_chart(rolling_chart(cb["rolling"], "roll_economy",
                                          f'{d["player"]}: economy over the last 10 innings', "Economy"))
            st.plotly_chart(phase_chart(phases["bowling"], "economy", f'{d["player"]}: economy by phase', "Economy"))
            df = pd.DataFrame(seasons["bowling"])
            st.dataframe(df.round(2), hide_index=True)


from core.home_away import get_home_away_stats

st.divider()
st.subheader("Home vs away")
st.caption("Home and away use each team's home grounds by season. Seasons played away from India (2009, 2020, 2021), "
           "the relocated 2022 season and the UAE leg of 2014 count as neutral.")
ha = get_home_away_stats(pid)
if not ha["ok"]:
    st.info(ha["error"])
else:
    hd = ha["data"]
    for w in ha["warnings"]:
        if ("batting" in w and show_bat) or ("bowling" in w and show_bowl):
            st.warning(w)
    if show_bat and "batting" in hd:
        st.markdown("**Batting**")
        cols = ["innings", "runs", "avg", "sr", "high_score", "fifties", "hundreds"]
        st.dataframe(pd.DataFrame(hd["batting"]).T[cols].round(2))
        g = hd["batting_home_minus_away"]
        if g["avg"] is not None and g["sr"] is not None:
            st.write(f'Home minus away: average {g["avg"]:+.1f}, strike rate {g["sr"]:+.1f}')
        st.plotly_chart(season_chart(ha["chart"]["batting"], f'{d["player"]}: batting at home, away and neutral',
                                     bar="avg", line="sr", bar_name="Average", line_name="Strike rate"))
    if show_bowl and "bowling" in hd:
        st.markdown("**Bowling**")
        cols = ["innings", "wickets", "economy", "avg", "sr", "best_figures"]
        st.dataframe(pd.DataFrame(hd["bowling"]).T[cols])
        g = hd["bowling_home_minus_away"]
        if g["economy"] is not None:
            st.write(f'Home minus away: economy {g["economy"]:+.2f}')
        st.plotly_chart(season_chart(ha["chart"]["bowling"], f'{d["player"]}: bowling at home, away and neutral',
                                     bar="wickets", line="economy", bar_name="Wickets", line_name="Economy"))

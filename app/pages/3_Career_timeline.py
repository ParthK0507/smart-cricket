import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.charts import form_chart, timeline_chart
from core.config import DATA_THROUGH
from core.player import get_career_stats
from core.resolve import resolve_player
from core.trends import get_career_trends

st.set_page_config(page_title="Career timeline", page_icon="🏏", layout="wide")
st.title("Career timeline")
st.caption(f"The ups and downs of a career | IPL data through {DATA_THROUGH}")

query = st.text_input("Player name", value="Virat Kohli", help="Try: kohli, dhoni, rohit sharma, bumrah, malinga")
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

trend_res = get_career_trends(pid)
if not trend_res["ok"]:
    st.error(trend_res["error"])
    st.stop()
d, charts = trend_res["data"], trend_res["chart"]
role = get_career_stats(pid)["data"]["role"]
bat, bowl = d.get("batting"), d.get("bowling")
show_bat = bool(bat) and role in ("batter", "all-rounder")
show_bowl = bool(bowl) and role in ("bowler", "all-rounder")
name = d["player"]

st.header(name)
for w in trend_res["warnings"]:
    st.warning(w)

tab_names = (["Batting"] if show_bat else []) + (["Bowling"] if show_bowl else [])
if not tab_names:
    st.warning("Not enough IPL data to draw a timeline for this player.")
    st.stop()
tabs = st.tabs(tab_names)


def years(values):
    return ", ".join(map(str, values)) or "none"


def fmt(v, digits=1):
    return "-" if v is None else f"{v:,.{digits}f}"


def season_cards(ev, unit):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Best season ({unit})", f'{ev["best_season"]["year"]} ({ev["best_season"]["value"]})')
    c2.metric("Worst season", f'{ev["worst_season"]["year"]} ({ev["worst_season"]["value"]})')
    j, k = ev["biggest_jump"], ev["biggest_drop"]
    c3.metric("Biggest jump", f'{j["from_year"]} to {j["to_year"]}', f'{j["change"]:+.2f}')
    c4.metric("Biggest drop", f'{k["from_year"]} to {k["to_year"]}', f'{k["change"]:+.2f}')


LEGEND = ("Green = peak seasons and red = slump seasons (more than one standard deviation from the player's own "
          "career mean, counting seasons with 6 or more innings). Shaded bands show the team.")

for tab_name, tab in zip(tab_names, tabs):
    with tab:
        if tab_name == "Batting":
            tb, cb = bat, charts["batting"]
            ev, tr = tb["events"], tb["trend"]
            peaks, slumps, mean = (), (), None
            if ev:
                peaks, slumps, mean = ev["peak_years"], ev["slump_years"], ev["career_mean"]
                season_cards(ev, "runs per innings")
            else:
                st.info("Peaks and slumps need at least 3 seasons with 6 or more innings.")
            st.plotly_chart(timeline_chart(tb["seasons"], tb["teams"], "runs_per_inn",
                                           f"{name}: runs per innings by season", "Runs per innings",
                                           peaks, slumps, mean))
            st.caption(LEGEND)

            bw, ww, rf = tb["best_window"], tb["worst_window"], tb["recent_form"]
            windows = []
            if bw:
                windows.append({"from": bw["from"], "to": bw["to"], "label": "best 10", "color": "green"})
            if ww:
                windows.append({"from": ww["from"], "to": ww["to"], "label": "worst 10", "color": "red"})
            choice = st.radio("Form metric (last 10 innings)", ["Strike rate", "Average"], horizontal=True,
                              key="tl_bat_metric")
            key, label = ("roll_sr", "Strike rate") if choice == "Strike rate" else ("roll_avg", "Average")
            st.plotly_chart(form_chart(cb["rolling"], key, f"{name}: {label.lower()} over the last 10 innings",
                                       label, windows))
            if bw and ww:
                st.write(f'**Best 10 innings:** {bw["runs"]} runs, average {fmt(bw["avg"])}, strike rate {fmt(bw["sr"])} '
                         f'({bw["from"]} to {bw["to"]})')
                st.write(f'**Worst 10 innings:** {ww["runs"]} runs, average {fmt(ww["avg"])}, strike rate {fmt(ww["sr"])} '
                         f'({ww["from"]} to {ww["to"]})')
            st.write(f'**Last 10 innings:** {rf["runs"]} runs, average {fmt(rf["avg"])}, strike rate {fmt(rf["sr"])} '
                     f'against a career average of {fmt(rf["career_avg"])} and strike rate of {fmt(rf["career_sr"])}')
            if tr:
                st.info(f'Strike rate in {years(tr["recent_years"])}: {tr["recent"]["sr"]} against {tr["earlier"]["sr"]} '
                        f'before ({tr["sr_change"]:+.1f}). The league moved {tr["league_sr_change"]:+.1f} over the '
                        f'same span, so measured against the league: {tr["direction"]}.')
            st.dataframe(pd.DataFrame(tb["seasons"]).round(2), hide_index=True)
        else:
            tb, cb = bowl, charts["bowling"]
            ev, tr = tb["events"], tb["trend"]
            peaks, slumps, mean = (), (), None
            if ev:
                peaks, slumps, mean = ev["peak_years"], ev["slump_years"], ev["career_mean"]
                season_cards(ev, "wickets per innings")
            else:
                st.info("Peaks and slumps need at least 3 seasons with 6 or more innings.")
            st.plotly_chart(timeline_chart(tb["seasons"], tb["teams"], "wkts_per_inn",
                                           f"{name}: wickets per innings by season", "Wickets per innings",
                                           peaks, slumps, mean))
            st.caption(LEGEND)
            st.plotly_chart(form_chart(cb["rolling"], "roll_economy", f"{name}: economy over the last 10 innings",
                                       "Economy"))
            eco, bw, ww, rf = tb["economy_extremes"], tb["best_window"], tb["worst_window"], tb["recent_form"]
            if eco:
                st.write(f'**Best economy season:** {eco["best"]["year"]} ({eco["best"]["economy"]}) | '
                         f'**Worst:** {eco["worst"]["year"]} ({eco["worst"]["economy"]})')
            if bw and ww:
                st.write(f'**Best 10 innings:** {bw["wickets"]} wickets, economy {fmt(bw["economy"], 2)} '
                         f'({bw["from"]} to {bw["to"]})')
                st.write(f'**Worst 10 innings:** {ww["wickets"]} wickets, economy {fmt(ww["economy"], 2)} '
                         f'({ww["from"]} to {ww["to"]})')
            st.write(f'**Last 10 innings:** {rf["wickets"]} wickets, economy {fmt(rf["economy"], 2)} '
                     f'against a career economy of {fmt(rf["career_economy"], 2)}')
            if tr:
                st.info(f'Economy in {years(tr["recent_years"])}: {tr["recent"]["economy"]} against {tr["earlier"]["economy"]} '
                        f'before ({tr["economy_change"]:+.2f}). The league moved {tr["league_economy_change"]:+.2f} over '
                        f'the same span, so measured against the league: {tr["direction"]}.')
            st.dataframe(pd.DataFrame(tb["seasons"]).round(2), hide_index=True)

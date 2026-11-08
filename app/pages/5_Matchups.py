import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.charts import season_chart
from core.config import DATA_THROUGH
from core.matchup import get_bowler_matchup
from core.opposition import get_opposition_stats
from core.resolve import resolve_player
from core.teams import _canonical_teams
from core.venue_stats import get_venue_stats
from core.venues import _canonical_venues

st.set_page_config(page_title="Matchups", page_icon="🏏", layout="wide")
st.title("Matchups")
st.caption(f"Head to head, against a team, and at a ground | IPL data through {DATA_THROUGH}")


def fmt(v, digits=1):
    return "-" if v is None else f"{v:,.{digits}f}"


def metric_row(items):
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        col.metric(label, "-" if value is None else value)


def pick(label, key, default=""):
    """One player box: returns a player id, or None when empty or not usable."""
    text = st.text_input(label, value=default, key=f"{key}_text")
    if not text.strip():
        return None
    res = resolve_player(text)
    if res["status"] == "not_found":
        st.error(f"No player found for '{text}'.")
        return None
    if res["status"] == "ambiguous":
        labels = {f'{c["player"]} ({c["years"]}, {c["team"]}, {c["matches"]} matches)': c["player_id"]
                  for c in res["candidates"]}
        return labels[st.selectbox(f"Which '{text}'?", list(labels), key=f"{key}_sel")]
    return res["player_id"]


def render_split(res, subject):
    """Shared layout for 'player against a team' and 'player at a ground'."""
    if not res["ok"]:
        st.warning(res["error"])
        return
    d, ch = res["data"], res["chart"]
    for w in res["warnings"]:
        st.info(w)
    bat, bowl = d.get("batting"), d.get("bowling")
    if bat:
        st.subheader(f'{d["player"]}: batting {subject}')
        hs = f'{bat["high_score"]}{"*" if bat["high_score_not_out"] else ""}'
        metric_row([("Innings", bat["innings"]), ("Runs", f'{bat["runs"]:,}'), ("Average", fmt(bat["avg"], 2)),
                    ("Strike rate", fmt(bat["sr"], 2)), ("High score", hs),
                    ("50s / 100s", f'{bat["fifties"]} / {bat["hundreds"]}')])
        st.caption(f'Career: average {fmt(bat["career_avg"], 2)}, strike rate {fmt(bat["career_sr"], 2)}')
        st.plotly_chart(season_chart(ch["batting"], f'Runs and strike rate by season, {subject}'))
        st.dataframe(pd.DataFrame.from_dict(bat["by_phase"], orient="index").round(2))
    if bowl:
        st.subheader(f'{d["player"]}: bowling {subject}')
        metric_row([("Innings", bowl["innings"]), ("Wickets", bowl["wickets"]), ("Economy", fmt(bowl["economy"], 2)),
                    ("Average", fmt(bowl["avg"], 2)), ("Strike rate", fmt(bowl["sr"], 1)),
                    ("Best", bowl["best_figures"])])
        st.caption(f'Career economy: {fmt(bowl["career_economy"], 2)}')
        st.plotly_chart(season_chart(ch["bowling"], f'Wickets and economy by season, {subject}', bar="wickets",
                                     line="economy", bar_name="Wickets", line_name="Economy"))
        st.dataframe(pd.DataFrame.from_dict(bowl["by_phase"], orient="index").round(2))


tab1, tab2, tab3 = st.tabs(["Batter vs bowler", "Player vs team", "Player at a ground"])

with tab1:
    c1, c2 = st.columns(2)
    with c1:
        batter = pick("Batter", "mu_bat", "Virat Kohli")
    with c2:
        bowler = pick("Bowler", "mu_bowl", "Rashid Khan")
    if batter and bowler:
        res = get_bowler_matchup(batter, bowler)
        if not res["ok"]:
            st.warning(res["error"])
        else:
            d = res["data"]
            for w in res["warnings"]:
                st.info(w)
            st.subheader(f'{d["batter"]} against {d["bowler"]}')
            metric_row([("Balls", d["balls"]), ("Runs", d["runs"]), ("Dismissals", d["dismissals"]),
                        ("Strike rate", fmt(d["strike_rate"], 2)), ("Average", fmt(d["average"], 2)),
                        ("Dot balls %", fmt(d["dot_pct"]))])
            st.write(f'Fours: {d["fours"]} | Sixes: {d["sixes"]} | Boundary runs: {d["boundary_run_pct"]}% | '
                     f'Balls per dismissal: {fmt(d["balls_per_dismissal"])}')
            st.info(f'Verdict (a rule of thumb from strike rate and how often he is dismissed): {d["verdict"]}')
            st.plotly_chart(season_chart(res["chart"], "Runs and strike rate by season"))
            st.dataframe(pd.DataFrame(d["by_phase"]).round(2), hide_index=True)

with tab2:
    c1, c2 = st.columns(2)
    with c1:
        p2 = pick("Player", "opp_player", "Virat Kohli")
    with c2:
        t = st.selectbox("Against team", _canonical_teams(), key="opp_team")
    if p2:
        render_split(get_opposition_stats(p2, t), f"against {t}")

with tab3:
    venues = _canonical_venues()
    c1, c2 = st.columns(2)
    with c1:
        p3 = pick("Player", "ven_player", "Rohit Sharma")
    with c2:
        g = st.selectbox("Ground", venues, index=venues.index("Wankhede Stadium, Mumbai"), key="ven_ground")
    if p3:
        render_split(get_venue_stats(p3, g), f"at {g}")

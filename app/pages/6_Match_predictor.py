import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.charts import ground_scores_chart, win_curve_chart
from core.config import DATA_THROUGH
from core.predict import predict_chase
from core.preview import get_match_preview
from core.teams import _canonical_teams
from core.venues import _canonical_venues

st.set_page_config(page_title="Match predictor", page_icon="🏏", layout="wide")
st.title("Match predictor")
st.caption(f"IPL data through {DATA_THROUGH}")


def fmt(v, digits=1):
    return "-" if v is None else f"{v:,.{digits}f}"


teams, venues = _canonical_teams(), _canonical_venues()
c1, c2, c3 = st.columns(3)
team1 = c1.selectbox("Team 1", teams, index=teams.index("Chennai Super Kings"))
team2 = c2.selectbox("Team 2", teams, index=teams.index("Mumbai Indians"))
venue = c3.selectbox("Ground", venues, index=venues.index("Wankhede Stadium, Mumbai"))
if team1 == team2:
    st.error("Pick two different teams.")
    st.stop()

tab_chase, tab_live, tab_preview = st.tabs(["After the first innings", "Live chase", "Match preview"])


with tab_chase:
    st.write("Once the first innings is over, how likely is the chasing team to win? "
             "The model compares the score with what is normal at this ground.")
    a, b = st.columns(2)
    bat_first = a.selectbox("Batting first", [team1, team2], key="bat_first")
    runs = b.number_input("First-innings score", min_value=40, max_value=300, value=170, step=1)
    chasing = team2 if bat_first == team1 else team1
    res = predict_chase(bat_first, chasing, venue, runs)
    if not res["ok"]:
        st.error(res["error"])
    else:
        d = res["data"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(f"{chasing} (chasing) win", f'{d["chase_win_prob"] * 100:.0f}%')
        m2.metric(f"{bat_first} (batting first) win", f'{d["bat_first_win_prob"] * 100:.0f}%')
        m3.metric("Par score here", fmt(d["par_score"]), f'{d["target_vs_par"]:+.0f} vs par', delta_color="off")
        m4.metric("Even odds at", f'{d["break_even_score"]:.0f}')
        st.write(f'Favourite: **{d["favourite"]}**. Each 10 extra runs on the target moves the chasing team by about '
                 f'{abs(d["swing_per_10_runs"]) * 100:.0f} percentage points.')
        for w in res["warnings"]:
            st.info(w)
        st.plotly_chart(win_curve_chart(res["chart"],
                                        f'Chasing team win chance by first-innings score, {venue.split(",")[0]}'))
        acc = d["model"]
        st.caption(f'How good is this? Tested on {acc["test_matches"]} matches from 2015 onward, always predicting '
                   f'from earlier matches only: {acc["accuracy"] * 100:.0f}% correct (give or take '
                   f'{acc["margin"] * 100:.1f} points), against about 53% for always picking the chasing team. '
                   f'Trained through {acc["trained_through"]}.')
        for n in d["notes"]:
            st.caption(n)
        st.caption("Why switching the teams changes little: we measured it. A 100-point rating edge for the chasing team (about twice the usual gap between two teams) was worth about +4 points of win chance, but the data cannot rule out zero (95% range -2 to +10), and adding the rating did not improve predictions in testing. The first-innings score against par moves the chance by about 8 points per 10 runs.")

with tab_preview:
    st.write("Facts before the toss. There is no win probability here, because team ratings, home advantage and "
             "the toss added no measurable accuracy when we tested them.")
    pv = get_match_preview(team1, team2, venue)
    if not pv["ok"]:
        st.error(pv["error"])
    else:
        d, g, h = pv["data"], pv["data"]["ground"], pv["data"]["head_to_head"]
        for hl in d["highlights"]:
            st.success(hl)

        st.subheader(f'The ground: {d["venue"]}')
        k = st.columns(5)
        k[0].metric("IPL matches here", g["matches"])
        k[1].metric("Par score", fmt(g["par_score"]))
        k[2].metric("Chasing team won", f'{fmt(g["chase_win_pct"])}%')
        k[3].metric("Since 2022", f'{fmt(g["since_2022"]["chase_win_pct"])}%',
                    f'{g["since_2022"]["matches"]} matches', delta_color="off")
        k[4].metric("Captains chose to field", f'{fmt(g["toss_field_pct"])}%')
        st.plotly_chart(ground_scores_chart(pv["chart"], "Average first-innings score by season"))

        st.subheader("Head to head")
        a, b = st.columns(2)
        for col, t in zip((a, b), (d["team1"], d["team2"])):
            col.metric(f"{t} wins", h["wins"][t],
                       f'since 2020: {h["since_2020"]["wins"][t]} of {h["since_2020"]["meetings"]}',
                       delta_color="off")
        if h["last_meetings"]:
            st.write("Last five meetings, oldest first:")
            st.dataframe(pd.DataFrame(h["last_meetings"]), hide_index=True)

        st.subheader("The teams")
        cols = st.columns(2)
        for col, t in zip(cols, d["teams"]):
            with col:
                st.markdown(f'**{t["team"]}**')
                st.write(f'Last 5: `{t["form_last5"]}` (most recent last)')
                st.write(f'Last 15: {t["wins_last15"]} wins from {t["of_last15"]}')
                ag = t["at_ground"]
                st.write(f'Here: {ag["wins"]} wins from {ag["matches"]}'
                         + ("" if ag["win_pct"] is None else f' ({ag["win_pct"]}%)'))
                st.write(f'At this ground in the latest season: {t["ground_status_latest_season"]}')
        for w in pv["warnings"]:
            st.warning(w)
        st.caption(f'Facts are computed from IPL matches up to {d["as_of"]}.')


from core.live import predict_live

with tab_live:
    st.write("During the second innings: enter the chasing team's score so far. The win chance comes from the "
             "situation (runs needed, balls left, wickets in hand) and the ground. It covers full 20-over chases, "
             "not rain-shortened ones.")
    la, lb, lc = st.columns(3)
    live_bat = la.selectbox("Batting first", [team1, team2], key="live_bat_first")
    live_first = lb.number_input("First-innings score", min_value=40, max_value=300, value=180, step=1, key="live_first")
    live_chasing = team2 if live_bat == team1 else team1
    lc.markdown(f"**Chasing:** {live_chasing}")
    ld, le, lf, lg = st.columns(4)
    live_runs = ld.number_input("Runs scored", min_value=0, max_value=400, value=85, step=1, key="live_runs")
    live_wk = le.number_input("Wickets lost", min_value=0, max_value=9, value=1, step=1, key="live_wk")
    live_ov = lf.number_input("Overs completed", min_value=0, max_value=19, value=10, step=1, key="live_ov")
    live_b = lg.number_input("Balls in the current over", min_value=0, max_value=5, value=0, step=1, key="live_b")

    res_l = predict_live(live_bat, live_chasing, venue, live_first, live_runs, live_wk, int(live_ov) * 6 + int(live_b))
    if not res_l["ok"]:
        st.error(res_l["error"])
    else:
        dl = res_l["data"]
        k1, k2 = st.columns(2)
        k1.metric(f"{live_chasing} (chasing) win", f'{dl["chase_win_prob"] * 100:.0f}%')
        k2.metric(f"{live_bat} (batting first) win", f'{dl["bat_first_win_prob"] * 100:.0f}%')
        st.progress(float(dl["chase_win_prob"]))
        for w in res_l["warnings"]:
            st.info(w)
        if dl["model_used"] == "live":
            st.write(f'**{dl["score"]} after {dl["overs"]} overs.** Needs {dl["runs_needed"]} from {dl["balls_left"]} '
                     f'balls: {dl["required_rate"]} an over required against {dl["current_rate"]} so far, with '
                     f'{dl["wickets_in_hand"]} wickets in hand. Par first-innings score at this ground: {fmt(dl["par_score"])}.')
            if dl["next_over"]:
                nxt = pd.DataFrame(dl["next_over"]).pivot(index="next_over_runs", columns="wickets_in_over",
                                                          values="chase_win_prob") * 100
                nxt.columns = ["no wicket" if k == 0 else "a wicket" for k in nxt.columns]
                nxt.index.name = "runs in the next over"
                st.write("What the next over could do to the chasing team's chances (%):")
                st.dataframe(nxt.round(0))
            mod = dl["model"]
            st.caption(f'Tested by walking forward season by season from 2015: at around {mod["at_overs"]} overs the '
                       f'model was right in {mod["accuracy"] * 100:.0f}% of {mod["test_states"]} situations (give or '
                       f'take {mod["margin"] * 100:.0f} points), against {mod["baseline_accuracy"] * 100:.0f}% from the '
                       f'first-innings score alone.')
            st.caption("Like the first-innings model, this uses the situation and the ground, not team names: team "
                       "strength added no measurable accuracy in testing.")
        else:
            st.info(dl["live_note"])

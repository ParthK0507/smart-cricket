import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.charts import bar_chart
from core.config import DATA_THROUGH
from core.data import table
from core.leaderboard import BAT_METRICS, BOWL_METRICS, get_leaderboard
from core.teams import _canonical_teams
from core.venues import _canonical_venues

st.set_page_config(page_title="Leaderboards", page_icon="🏏", layout="wide")
st.title("Leaderboards")
st.caption(f"IPL data through {DATA_THROUGH}")

YEARS = sorted(int(y) for y in table("matches")["year"].unique())

c1, c2, c3 = st.columns(3)
role = c1.radio("Role", ["Batting", "Bowling"], horizontal=True).lower()
spec = BAT_METRICS if role == "batting" else BOWL_METRICS
metric_labels = {v[0]: k for k, v in spec.items()}
metric = metric_labels[c2.selectbox("Metric", list(metric_labels))]
top = c3.slider("How many players", 5, 25, 10)

f1, f2, f3, f4 = st.columns(4)
season_mode = f1.selectbox("Seasons", ["All seasons", "One season", "Range"])
kwargs = {}
if season_mode == "One season":
    kwargs["year"] = f1.selectbox("Season", YEARS, index=len(YEARS) - 1)
elif season_mode == "Range":
    lo, hi = f1.select_slider("Season range", options=YEARS, value=(YEARS[0], YEARS[-1]))
    kwargs["year_from"], kwargs["year_to"] = lo, hi

teams = ["Any"] + _canonical_teams()
team = f2.selectbox("Batting team" if role == "batting" else "Bowling team", teams)
opposition = f3.selectbox("Against", teams)
venue = f4.selectbox("Ground", ["Any"] + _canonical_venues())
if team != "Any":
    kwargs["team"] = team
if opposition != "Any":
    kwargs["opposition"] = opposition
if venue != "Any":
    kwargs["venue"] = venue

min_inn = st.number_input("Minimum innings (average, strike rate, economy and consistency only)",
                          min_value=0, max_value=300, value=0, help="0 means automatic: 20 for all seasons, "
                          "8 for one season, 5 when other filters are on.")
if min_inn > 0:
    kwargs["min_innings"] = int(min_inn)

res = get_leaderboard(metric, role=role, top=top, **kwargs)
if not res["ok"]:
    st.warning(res["error"])
    st.stop()
d = res["data"]
for w in res["warnings"]:
    st.info(w)

st.subheader(f'{d["label"]}: top {len(d["rows"])}')
if d["min_innings"] is not None:
    st.caption(f'Minimum {d["min_innings"]} innings to qualify. {d["qualified"]} players qualify.')
st.plotly_chart(bar_chart(res["chart"]["x"], res["chart"]["y"], d["label"], d["label"]))
df = pd.DataFrame(d["rows"]).drop(columns=["player_id"])
st.dataframe(df.round(2), hide_index=True)

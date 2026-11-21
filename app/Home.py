import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from core.config import DATA_THROUGH
from core.data import preload

st.set_page_config(page_title="Smart Cricket", page_icon="🏏", layout="wide")


@st.cache_resource(show_spinner="Loading IPL data...")
def load():
    return {name: df.shape for name, df in preload().items()}


shapes = load()

st.title("🏏 Smart Cricket")
st.write("Explore every IPL ball bowled, from the first match in 2008. Look up a player, compare players, "
         "and see a career's ups and downs.")
st.caption(f"Data through {DATA_THROUGH}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Matches", f'{shapes["matches"][0]:,}')
c2.metric("Deliveries", f'{shapes["balls"][0]:,}')
c3.metric("Batters", f'{shapes["career_batting"][0]:,}')
c4.metric("Bowlers", f'{shapes["career_bowling"][0]:,}')

st.info("Use the pages in the sidebar: Player profile, Compare, Career timeline, Leaderboards, Matchups and Match predictor. "
        "On the Ask page you can type a question in your own words.")
st.caption("Match predictions are model estimates, tested on past seasons. The Ask page uses an AI assistant that can be "
           "busy or slow; when it is, the dashboard pages always show the same numbers.")

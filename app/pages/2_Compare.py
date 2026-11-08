import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.charts import radar_chart
from core.compare import compare_players
from core.config import DATA_THROUGH
from core.resolve import resolve_player

st.set_page_config(page_title="Compare players", page_icon="🏏", layout="wide")
st.title("Compare players")
st.caption(f"IPL data through {DATA_THROUGH}")


def pick(slot, default=""):
    """One player slot: returns a player id, None (empty slot) or 'error'."""
    text = st.text_input(f"Player {slot}", value=default, key=f"cmp_text_{slot}")
    if not text.strip():
        return None
    res = resolve_player(text)
    if res["status"] == "not_found":
        st.error(f"No player found for '{text}'.")
        return "error"
    if res["status"] == "ambiguous":
        labels = {f'{c["player"]} ({c["years"]}, {c["team"]}, {c["matches"]} matches)': c["player_id"]
                  for c in res["candidates"]}
        return labels[st.selectbox(f"Which '{text}'?", list(labels), key=f"cmp_sel_{slot}")]
    return res["player_id"]


cols = st.columns(4)
defaults = ["Virat Kohli", "Suresh Raina", "", ""]
picked = []
for i, col in enumerate(cols):
    with col:
        picked.append(pick(i + 1, defaults[i]))

role_label = st.radio("Compare as", ["Auto", "Batters", "Bowlers"], horizontal=True,
                      help="Auto picks batting or bowling from the players' roles. Choose one for all-rounders.")
role = {"Auto": "auto", "Batters": "batting", "Bowlers": "bowling"}[role_label]

if "error" in picked:
    st.stop()
ids = [p for p in picked if p]
if len(ids) < 2:
    st.info("Enter at least two players.")
    st.stop()

res = compare_players(ids, role=role)
if not res["ok"]:
    st.error(res["error"])
    for c in res["candidates"]:
        st.write(f'{c.get("player", "")}: {c.get("role", "")}')
    st.stop()

d = res["data"]
names = d["players"]
for w in res["warnings"]:
    st.warning(w)

summary = ", ".join(f"{n} {d['wins'][n]}" for n in names)
st.subheader(f"Ahead on: {summary} (of {d['scored_metrics']} metrics, {d['ties']} tied)")
st.caption("This counts who leads on each metric. It is a scorecard, not a verdict: role, era and sample size matter.")

rows = [{"Metric": m["label"], **{n: m["values"][n] for n in names}, "Leader": m["winner"]}
        for m in d["metrics"].values()]
st.dataframe(pd.DataFrame(rows).round(2), hide_index=True)

st.plotly_chart(radar_chart(res["chart"]["radar"], " vs ".join(names)))

st.subheader("Career context")
st.dataframe(pd.DataFrame(d["context"]).astype(str), hide_index=False)

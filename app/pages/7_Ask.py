import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from agents.service import answer
from app import render
from core.config import DATA_THROUGH

st.set_page_config(page_title="Ask", page_icon="🏏", layout="wide")
st.title("Ask")
st.caption(f"Ask about IPL players, teams, grounds and matches in your own words. IPL data through {DATA_THROUGH}.")

EXAMPLES = ["Compare Kohli and Raina", "Top 5 run scorers in 2016", "Kohli vs Ashwin",
            "Has Kohli improved his strike rate recently?", "CSK vs MI at Wankhede", "Tell me about Bumrah"]

if "sid" not in st.session_state:
    st.session_state["sid"] = uuid.uuid4().hex
if "history" not in st.session_state:
    st.session_state["history"] = []

with st.expander("Example questions"):
    cols = st.columns(3)
    for i, ex in enumerate(EXAMPLES):
        cols[i % 3].button(ex, key=f"ex_{i}", on_click=lambda e=ex: st.session_state.update(pending=e))
    if st.button("Clear the conversation", key="clear"):
        st.session_state["history"] = []
        st.rerun()

render.reset_keys()
for m in st.session_state["history"]:
    with st.chat_message(m["role"]):
        if m["role"] == "user":
            st.write(m["text"])
        else:
            render.show(m["out"])

typed = st.chat_input("Ask about a player, a team, a ground or a match...")
pending = st.session_state.pop("pending", None)
question = typed or pending
if question:
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("Checking the numbers..."):
            out = answer(question, st.session_state["sid"])
        render.show(out)
    st.session_state["history"] = (st.session_state["history"]
                                   + [{"role": "user", "text": question}, {"role": "assistant", "out": out}])[-12:]

st.caption("Every number comes from the same verified tables as the dashboard pages. Predictions are model estimates.")

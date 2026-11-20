import operator
from typing import Annotated

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from typing_extensions import TypedDict

from agents.analysts import run_agent
from agents.plan import Understanding, make_plan


class AskState(TypedDict, total=False):
    understanding: dict
    steps: list
    clarify: str
    results: Annotated[list, operator.add]       # parallel analysts append here
    answer: dict


def plan_node(state):
    return make_plan(Understanding(**state["understanding"]))


def route(state):
    """Nothing to run (or a question for the user): stop. Otherwise one parallel branch per analyst step."""
    if state.get("clarify") or not state.get("steps"):
        return END
    return [Send("run_step", {"index": i, **s}) for i, s in enumerate(state["steps"])]


def run_step(step):
    r = run_agent(step["agent"], step["args"])
    r["index"] = step["index"]
    return {"results": [r]}


def aggregate(state):
    res = sorted(state["results"], key=lambda r: r["index"])      # parallel branches finish in any order
    return {"answer": {"ok": any(r["ok"] for r in res), "agents": [r["agent"] for r in res], "results": res,
                       "insights": [i for r in res for i in r["insights"]],
                       "warnings": [w for r in res for w in r["warnings"]],
                       "errors": [e for r in res for e in r["errors"]]}}


def build_graph():
    g = StateGraph(AskState)
    g.add_node("plan", plan_node)
    g.add_node("run_step", run_step)
    g.add_node("aggregate", aggregate)
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", route, ["run_step", END])
    g.add_edge("run_step", "aggregate")
    g.add_edge("aggregate", END)
    return g.compile()


GRAPH = build_graph()


def ask(understanding: dict) -> dict:
    return GRAPH.invoke({"understanding": understanding})

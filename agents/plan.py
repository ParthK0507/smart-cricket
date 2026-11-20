from typing import Literal, Optional

from pydantic import BaseModel, Field

from core.leaderboard import BAT_METRICS, BOWL_METRICS
from core.player import get_career_stats
from core.resolve import resolve_player
from core.teams import resolve_team
from core.venues import resolve_venue

Intent = Literal["player_profile", "trend", "compare", "matchup", "opposition", "venue", "leaderboard",
                 "preview", "chase", "live", "out_of_scope"]
MAX_STEPS = 6
OUT_OF_SCOPE = ("I can answer questions about IPL cricket from 2008 to 2025: player profiles and career trends, "
                "comparisons, batter against bowler, performance against a team or at a ground, leaderboards, "
                "and match predictions.")


class Understanding(BaseModel):
    """What the user is asking. The language model fills this in; code turns it into analyst steps."""
    intents: list[Intent] = Field(description="1 to 3 intents. Use out_of_scope when the question is not about IPL cricket.")
    players: list[str] = Field(default_factory=list,
                               description="Players exactly as the user wrote them. For a matchup, the batter first, then the bowler.")
    teams: list[str] = Field(default_factory=list,
                             description="Teams as written. For a preview: the two teams. For chase or live: the team batting first, then the chasing team.")
    venues: list[str] = Field(default_factory=list, description="Grounds as written.")
    metric: Optional[str] = Field(default=None, description="Leaderboard statistic: runs, avg, sr, sixes, fours, fifties, hundreds, wickets, economy, five_w ...")
    role: Literal["batting", "bowling", "auto"] = "auto"
    year: Optional[int] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    top: int = 10
    first_innings_runs: Optional[int] = None
    runs: Optional[int] = Field(default=None, description="Chasing team's score so far.")
    wickets: Optional[int] = Field(default=None, description="Chasing team's wickets lost.")
    balls_bowled: Optional[int] = Field(default=None, description="Legal balls bowled so far in the chase.")


def _lb_role(u):
    if u.role != "auto":
        return u.role
    return "bowling" if (u.metric in BOWL_METRICS and u.metric not in BAT_METRICS) else "batting"


def _role_of(text):
    r = get_career_stats(text)
    return r["data"]["role"] if r["ok"] else None


def build_steps(u):
    """Understanding -> list of analyst steps, plus any problems (missing details the user must supply)."""
    steps, problems = [], []
    P, T, V = u.players, u.teams, u.venues

    def add(agent, **args):
        s = {"agent": agent, "args": args}
        if s not in steps:
            steps.append(s)

    intents = list(u.intents)
    if "preview" in intents and "chase" not in intents and "live" not in intents and u.first_innings_runs is not None:
        live = u.runs is not None and u.wickets is not None and u.balls_bowled is not None
        intents[intents.index("preview")] = "live" if live else "chase"      # a score means a chase, not a preview
    for intent in intents:
        if intent == "out_of_scope":
            problems.append(OUT_OF_SCOPE)
        elif intent in ("player_profile", "trend", "opposition", "venue") and not P:
            problems.append("Which player do you mean?")
        elif intent == "player_profile":
            add("player_analyst", player=P[0], year=u.year)
        elif intent == "trend":
            for p in P[:3]:
                add("trend_analyst", player=p)
        elif intent == "compare":
            if len(P) < 2:
                problems.append("Which players should I compare? Name at least two.")
            else:
                pair = P[:2]
                roles = [_role_of(x) for x in pair] if len(P) == 2 and u.role == "auto" else []
                if roles == ["batter", "bowler"]:       # a batter and a bowler cannot be compared: show their matchup
                    add("matchup_analyst", batter=pair[0], bowler=pair[1])
                elif roles == ["bowler", "batter"]:
                    add("matchup_analyst", batter=pair[1], bowler=pair[0])
                else:
                    add("player_comparator", players=P[:4], role=u.role)
        elif intent == "matchup":
            if len(P) < 2:
                problems.append("Which batter and which bowler? Name both.")
            else:
                add("matchup_analyst", batter=P[0], bowler=P[1])
        elif intent == "opposition":
            for p in P[:3]:
                add("opposition_analyst", player=p, team=T[0] if T else None)
        elif intent == "venue":
            for p in P[:3]:
                add("venue_analyst", player=p, venues=V[:3])
        elif intent == "leaderboard":
            role = _lb_role(u)
            if not u.metric:
                problems.append("Which statistic should the leaderboard rank?")
            elif u.metric not in (BAT_METRICS if role == "batting" else BOWL_METRICS):
                options = sorted(BAT_METRICS if role == "batting" else BOWL_METRICS)
                problems.append(f"I can't rank '{u.metric}' for {role}. I can rank: {', '.join(options)}.")
            else:
                f = {"year": u.year, "year_from": u.year_from, "year_to": u.year_to,
                     "team": T[0] if T else None, "venue": V[0] if V else None}
                add("leaderboard_analyst", metric=u.metric, role=role, top=u.top,
                    **{k: v for k, v in f.items() if v is not None})
        elif intent == "preview":
            if len(T) < 2 or not V:
                problems.append("A match preview needs two teams and a ground.")
            else:
                add("match_predictor", mode="preview", team1=T[0], team2=T[1], venue=V[0])
        elif intent in ("chase", "live"):
            need = [len(T) >= 2, bool(V), u.first_innings_runs is not None]
            if intent == "live":
                need += [u.runs is not None, u.wickets is not None, u.balls_bowled is not None]
            if not all(need):
                problems.append("A chase prediction needs the team batting first, the chasing team, the ground and the "
                                "first-innings score" + (", plus the chasing team's runs, wickets and balls bowled."
                                                         if intent == "live" else "."))
            else:
                args = dict(mode=intent, batting_first=T[0], chasing=T[1], venue=V[0],
                            first_innings_runs=u.first_innings_runs)
                if intent == "live":
                    args.update(runs=u.runs, wickets=u.wickets, balls_bowled=u.balls_bowled)
                add("match_predictor", **args)
    return steps[:MAX_STEPS], problems


def check_entities(u):
    """Resolve every name the user typed; ambiguous or unknown names become a clarifying question."""
    issues = []
    for text in u.players:
        r = resolve_player(text)
        if r["status"] == "not_found":
            issues.append(f"I couldn't find a player called '{text}'.")
        elif r["status"] == "ambiguous":
            names = "; ".join(f'{c["player"]} ({c["years"]}, {c["team"]})' for c in r["candidates"][:5])
            issues.append(f"Which '{text}' do you mean? {names}.")
    for text in u.teams:
        r = resolve_team(text)
        if r["status"] == "not_found":
            issues.append(f"I couldn't find a team called '{text}'.")
        elif r["status"] == "ambiguous":
            issues.append(f"Which '{text}' do you mean: {' or '.join(r['candidates'])}?")
    for text in u.venues:
        r = resolve_venue(text)
        if r["status"] == "not_found":
            issues.append(f"I couldn't find a ground called '{text}'.")
        elif r["status"] == "ambiguous":
            issues.append(f"Which ground do you mean: {'; '.join(r['candidates'])}?")
    return issues


def make_plan(u):
    steps, problems = build_steps(u)
    issues = check_entities(u)
    clarify = " ".join(issues) if issues else " ".join(problems)
    return {"steps": [] if clarify else steps, "clarify": clarify}

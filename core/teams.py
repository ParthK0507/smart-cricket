import re

from rapidfuzz import fuzz, process

from core.data import table

_ALIAS_SPEC = {
    "Chennai Super Kings": ["csk", "chennai", "super kings"],
    "Mumbai Indians": ["mi", "mumbai"],
    "Royal Challengers Bengaluru": ["rcb", "bangalore", "bengaluru", "royal challengers"],
    "Kolkata Knight Riders": ["kkr", "kolkata", "knight riders"],
    "Sunrisers Hyderabad": ["srh", "sunrisers"],
    "Delhi Capitals": ["dc", "dd", "delhi", "delhi daredevils"],
    "Punjab Kings": ["pbks", "kxip", "punjab", "kings xi punjab", "kings xi"],
    "Rajasthan Royals": ["rr", "rajasthan"],
    "Gujarat Titans": ["gt", "titans"],
    "Lucknow Super Giants": ["lsg", "lucknow"],
    "Deccan Chargers": ["dch", "deccan", "chargers"],
    "Pune Warriors": ["pwi", "warriors"],
    "Gujarat Lions": ["gl", "lions"],
    "Kochi Tuskers Kerala": ["ktk", "kochi", "tuskers"],
    "Rising Pune Supergiant": ["rps", "supergiant", "supergiants"],
}
TEAM_ALIASES = {a: [team] for team, al in _ALIAS_SPEC.items() for a in al}
TEAM_ALIASES.update({                       # names shared by two franchises
    "gujarat": ["Gujarat Titans", "Gujarat Lions"],
    "pune": ["Pune Warriors", "Rising Pune Supergiant"],
    "hyderabad": ["Sunrisers Hyderabad", "Deccan Chargers"],
})


def _canonical_teams():
    m = table("matches")
    return sorted(set(m["team1"]) | set(m["team2"]))


def _team_result(teams):
    if len(teams) == 1:
        return {"status": "ok", "team": teams[0], "candidates": teams}
    return {"status": "ambiguous", "candidates": teams}


def resolve_team(text):
    """status is 'ok' (one team), 'ambiguous' (several franchises share the name) or 'not_found'."""
    q = " ".join(re.sub(r"[^a-z ]", " ", (text or "").lower()).split())
    if not q:
        return {"status": "not_found", "candidates": []}
    if q in TEAM_ALIASES:
        return _team_result(TEAM_ALIASES[q])
    canon = {c.lower(): c for c in _canonical_teams()}
    if q in canon:
        return _team_result([canon[q]])
    best = process.extractOne(q, list(TEAM_ALIASES) + list(canon), scorer=fuzz.WRatio, score_cutoff=82)
    if best is None:
        return {"status": "not_found", "candidates": []}
    key = best[0]
    return _team_result(TEAM_ALIASES[key] if key in TEAM_ALIASES else [canon[key]])

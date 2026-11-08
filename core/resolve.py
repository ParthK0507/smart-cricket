import re
from functools import lru_cache

from rapidfuzz import fuzz, process

from core.data import table

# what people type -> canonical name in the data (extend freely)
NICKNAMES = {
    "msd": "MS Dhoni", "thala": "MS Dhoni", "mahi": "MS Dhoni", "mahendra": "MS Dhoni",
    "hitman": "RG Sharma", "rohit": "RG Sharma", "virat": "V Kohli", "king kohli": "V Kohli",
    "sky": "SA Yadav", "jaddu": "RA Jadeja", "abd": "AB de Villiers", "mr 360": "AB de Villiers",
    "gayle": "CH Gayle", "universe boss": "CH Gayle", "bumrah": "JJ Bumrah",
    "hardik": "HH Pandya", "ashwin": "R Ashwin",
}


def _tokens(text):
    text = re.sub(r"\[.*?\]", " ", text.lower())          # drop the "[0bf1]" id tag
    return re.sub(r"[^a-z ]", " ", text).split()


@lru_cache(maxsize=1)
def _index():
    """One row per player id: name, matches, years, latest team."""
    pl = table("players").dropna(subset=["player_id"])
    m = table("matches")[["match_id", "match_seq", "year"]]
    pl = pl.merge(m, on="match_id").sort_values("match_seq")
    idx = (pl.groupby("player_id")
             .agg(name=("player", "last"), matches=("match_id", "nunique"),
                  first_year=("year", "min"), last_year=("year", "max"),
                  team=("team", "last"))
             .reset_index())
    idx["lname"] = idx["name"].str.lower()
    idx["base"] = idx["lname"].str.replace(r"\s*\[.*?\]", "", regex=True)
    idx["toks"] = idx["name"].map(_tokens)
    idx["surname"] = idx["toks"].map(lambda t: t[-1] if t else "")
    return idx


def _pack(rows, status, match_type=None):
    rows = rows.sort_values("matches", ascending=False)
    cands = [{"player": r["name"], "player_id": r["player_id"], "matches": int(r["matches"]),
              "years": f'{r["first_year"]}-{r["last_year"]}', "team": r["team"]}
             for r in rows.head(5).to_dict("records")]
    if status == "ok":
        top = cands[0]
        return {"status": "ok", "player": top["player"], "player_id": top["player_id"],
                "match_type": match_type, "candidates": cands[:1]}
    return {"status": status, "candidates": cands}


def resolve_player(query: str) -> dict:
    """status is 'ok' (one player), 'ambiguous' (ask the user, candidates listed) or 'not_found'."""
    idx = _index()
    q = (query or "").strip().lower()
    qt = _tokens(q)
    if not qt:
        return {"status": "not_found", "candidates": []}

    # 1) nickname
    if q in NICKNAMES:
        hit = idx[idx["name"] == NICKNAMES[q]]
        if len(hit):
            return _pack(hit, "ok", "nickname")

    # 2) exact name: compare without the id tag first, so players who share a name are caught
    hit = idx[idx["base"] == q]
    if len(hit) == 1:
        return _pack(hit, "ok", "exact")
    if len(hit) > 1:                      # two real players share this name
        return _pack(hit, "ambiguous")
    hit = idx[idx["lname"] == q]          # the user typed the tag, e.g. "harmeet singh [0bf1]"
    if len(hit) == 1:
        return _pack(hit, "ok", "exact")

    # 3) surname, then a typo-tolerant surname match
    cands, match_type = idx[idx["surname"] == qt[-1]], "surname"
    if not len(cands):
        best = process.extractOne(qt[-1], idx["surname"].unique().tolist(),
                                  scorer=fuzz.ratio, score_cutoff=75)
        if best is None:
            return {"status": "not_found", "candidates": []}
        cands, match_type = idx[idx["surname"] == best[0]], "fuzzy"

    # 4) if a first name was typed, use its first letter to narrow down
    if len(qt) > 1:
        init = cands[cands["toks"].map(lambda t: bool(t) and t[0][0] == qt[0][0])]
        if len(init):
            cands = init

    if len(cands) == 1:
        return _pack(cands, "ok", match_type)
    ranked = cands.sort_values("matches", ascending=False)
    top, second = ranked.iloc[0]["matches"], ranked.iloc[1]["matches"]
    factor = 3 if len(qt) > 1 else 5          # a bare surname needs a bigger lead
    if top >= factor * second:
        return _pack(ranked.head(1), "ok", "dominant" if len(qt) == 1 else match_type)
    return _pack(ranked, "ambiguous")
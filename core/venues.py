import re
from functools import lru_cache

from rapidfuzz import fuzz, process

from core.data import table

_STOP = {"stadium", "ground", "cricket", "the", "international"}

_ALIAS_SPEC = {
    "Eden Gardens, Kolkata": ["eden", "kolkata"],
    "Wankhede Stadium, Mumbai": ["wankhede"],
    "M Chinnaswamy Stadium, Bengaluru": ["chinnaswamy", "bangalore", "bengaluru"],
    "Arun Jaitley Stadium, Delhi": ["feroz shah kotla", "kotla", "arun jaitley", "delhi"],
    "Rajiv Gandhi International Stadium, Hyderabad": ["uppal", "rajiv gandhi", "hyderabad"],
    "MA Chidambaram Stadium, Chennai": ["chepauk", "chidambaram", "chennai"],
    "Sawai Mansingh Stadium, Jaipur": ["sawai mansingh", "jaipur"],
    "PCA IS Bindra Stadium, Mohali": ["mohali", "bindra", "pca"],
    "Narendra Modi Stadium, Ahmedabad": ["motera", "narendra modi", "sardar patel", "ahmedabad"],
    "MCA Stadium, Pune": ["mca", "gahunje", "subrata roy sahara", "pune"],
    "Dr DY Patil Sports Academy, Navi Mumbai": ["dy patil", "navi mumbai", "patil"],
    "Brabourne Stadium, Mumbai": ["brabourne"],
    "Dubai International Cricket Stadium, Dubai": ["dubai"],
    "Sheikh Zayed Stadium, Abu Dhabi": ["abu dhabi", "zayed"],
    "Sharjah Cricket Stadium, Sharjah": ["sharjah"],
    "Ekana Cricket Stadium, Lucknow": ["ekana", "lucknow"],
    "ACA-VDCA Stadium, Visakhapatnam": ["visakhapatnam", "vizag", "vdca"],
    "HPCA Stadium, Dharamsala": ["dharamsala", "dharamshala", "hpca"],
    "Maharaja Yadavindra Singh Stadium, Mullanpur": ["mullanpur", "new chandigarh"],
    "Kingsmead, Durban": ["durban"],
    "SuperSport Park, Centurion": ["centurion"],
    "New Wanderers Stadium, Johannesburg": ["wanderers", "johannesburg"],
    "St George's Park, Gqeberha": ["st georges park", "st george", "port elizabeth", "gqeberha"],
    "Newlands, Cape Town": ["cape town"],
    "De Beers Diamond Oval, Kimberley": ["de beers", "kimberley"],
    "Buffalo Park, East London": ["east london"],
    "OUTsurance Oval, Bloemfontein": ["outsurance", "bloemfontein"],
    "Saurashtra Cricket Association Stadium, Rajkot": ["rajkot", "saurashtra"],
    "Holkar Cricket Stadium, Indore": ["indore", "holkar"],
    "JSCA International Stadium Complex, Ranchi": ["ranchi", "jsca"],
    "Barabati Stadium, Cuttack": ["cuttack", "barabati"],
    "Shaheed Veer Narayan Singh Stadium, Raipur": ["raipur"],
    "Nehru Stadium, Kochi": ["kochi"],
    "Barsapara Cricket Stadium, Guwahati": ["guwahati", "barsapara"],
    "Green Park, Kanpur": ["kanpur"],
    "Vidarbha Cricket Association Stadium, Nagpur": ["nagpur", "vidarbha", "jamtha"],
}
_AMBIGUOUS = {                      # a city with more than one IPL ground
    "mumbai": ["Wankhede Stadium, Mumbai", "Brabourne Stadium, Mumbai",
               "Dr DY Patil Sports Academy, Navi Mumbai"],
    "chandigarh": ["PCA IS Bindra Stadium, Mohali", "Maharaja Yadavindra Singh Stadium, Mullanpur"],
}


def _norm(text):
    text = re.sub(r"[^a-z ]", " ", (text or "").lower())
    return " ".join(w for w in text.split() if w not in _STOP)


def _canonical_venues():
    return sorted(table("matches")["venue"].unique())


@lru_cache(maxsize=1)
def _build_keys():
    keys = {}

    def add(key, venue):
        key = _norm(key)
        if key:
            keys.setdefault(key, [])
            if venue not in keys[key]:
                keys[key].append(venue)

    for venue in _canonical_venues():
        add(venue, venue)
        add(venue.split(",")[0], venue)
    for venue, aliases in _ALIAS_SPEC.items():
        for a in aliases:
            add(a, venue)
    for key, venues in _AMBIGUOUS.items():
        keys[_norm(key)] = list(venues)
    return keys


def _venue_result(venues):
    if len(venues) == 1:
        return {"status": "ok", "venue": venues[0], "candidates": venues}
    return {"status": "ambiguous", "candidates": venues}


def resolve_venue(text):
    """status is 'ok' (one ground), 'ambiguous' (a city with several grounds) or 'not_found'."""
    q = _norm(text)
    if not q:
        return {"status": "not_found", "candidates": []}
    keys = _build_keys()
    if q in keys:
        return _venue_result(keys[q])
    best = process.extractOne(q, list(keys), scorer=fuzz.WRatio, score_cutoff=85)
    if best is None:
        return {"status": "not_found", "candidates": []}
    return _venue_result(keys[best[0]])

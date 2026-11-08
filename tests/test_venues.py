import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.venues import resolve_venue, _canonical_venues, _ALIAS_SPEC

fails = 0


def check(label, ok, detail=""):
    global fails
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label} {detail}")


CASES = [
    ("wankhede", "ok", "Wankhede Stadium, Mumbai"),
    ("Wankhede Stadium", "ok", "Wankhede Stadium, Mumbai"),
    ("kotla", "ok", "Arun Jaitley Stadium, Delhi"),
    ("Feroz Shah Kotla", "ok", "Arun Jaitley Stadium, Delhi"),
    ("chepauk", "ok", "MA Chidambaram Stadium, Chennai"),
    ("chinnaswamy", "ok", "M Chinnaswamy Stadium, Bengaluru"),
    ("bangalore", "ok", "M Chinnaswamy Stadium, Bengaluru"),
    ("eden gardens", "ok", "Eden Gardens, Kolkata"),
    ("mohali", "ok", "PCA IS Bindra Stadium, Mohali"),
    ("motera", "ok", "Narendra Modi Stadium, Ahmedabad"),
    ("uppal", "ok", "Rajiv Gandhi International Stadium, Hyderabad"),
    ("vizag", "ok", "ACA-VDCA Stadium, Visakhapatnam"),
    ("wankhde", "ok", "Wankhede Stadium, Mumbai"),
    ("mumbai", "ambiguous", None),
    ("chandigarh", "ambiguous", None),
    ("xyzzy", "not_found", None),
]
for q, status, venue in CASES:
    r = resolve_venue(q)
    check(f"{q!r:20}", r["status"] == status and (venue is None or r.get("venue") == venue),
          f"-> {r['status']} {r.get('venue', '')}")

venues = _canonical_venues()
check("36 canonical venues", len(venues) == 36, f"({len(venues)})")
bad = [v for v in venues if resolve_venue(v).get("venue") != v]
check("every canonical name resolves to itself", not bad, str(bad))
missing = [v for v in _ALIAS_SPEC if v not in venues]
check("every alias target exists in the data", not missing, str(missing))

print("\nfailures:", fails)

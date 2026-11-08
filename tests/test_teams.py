import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.teams import resolve_team

CASES = [
    ("csk", "ok", "Chennai Super Kings"), ("Chennai", "ok", "Chennai Super Kings"),
    ("rcb", "ok", "Royal Challengers Bengaluru"), ("royal challengers bangalore", "ok", "Royal Challengers Bengaluru"),
    ("delhi daredevils", "ok", "Delhi Capitals"), ("pbks", "ok", "Punjab Kings"),
    ("kings xi punjab", "ok", "Punjab Kings"), ("Mumbai Indians", "ok", "Mumbai Indians"),
    ("srh", "ok", "Sunrisers Hyderabad"), ("deccan", "ok", "Deccan Chargers"),
    ("chenai super kings", "ok", "Chennai Super Kings"),
    ("gujarat", "ambiguous", None), ("pune", "ambiguous", None), ("hyderabad", "ambiguous", None),
    ("xyzzy", "not_found", None),
]
fails = 0
for q, status, team in CASES:
    r = resolve_team(q)
    ok = r["status"] == status and (team is None or r.get("team") == team)
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {q!r:30} -> {r['status']:10} {r.get('team', '')}")
print("\nfailures:", fails)

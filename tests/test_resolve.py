import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.resolve import resolve_player

MUST_PASS = [
    ("Virat Kohli", "ok", "V Kohli"), ("kohli", "ok", "V Kohli"), ("Kholi", "ok", "V Kohli"),
    ("msd", "ok", "MS Dhoni"), ("dhoni", "ok", "MS Dhoni"), ("Rohit Sharma", "ok", "RG Sharma"),
    ("jasprit bumrah", "ok", "JJ Bumrah"), ("abd", "ok", "AB de Villiers"),
    ("sharma", "ambiguous", None), ("khan", "ambiguous", None), ("xyzzy", "not_found", None),
    ("Harmeet Singh", "ambiguous", None),
]
JUST_SHOW = ["Harmeet Singh", "Rashid Khan", "Ishant Sharma", "KL Rahul", "Navdeep Saini", "Arshad Khan"]

fails = 0
for q, status, name in MUST_PASS:
    r = resolve_player(q)
    ok = r["status"] == status and (name is None or r.get("player") == name)
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {q!r:18} -> {r['status']:10} {r.get('player', '')}")
print("\nfailures:", fails)

print("\n--- just look at these ---")
for q in JUST_SHOW:
    r = resolve_player(q)
    print(q, "->", r["status"], [(c["player"], c["years"], c["team"]) for c in r["candidates"]])
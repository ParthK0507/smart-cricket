import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.data import table
from core.preview import get_match_preview

fails = 0


def check(label, ok):
    global fails
    ok = bool(ok)
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}")


m, b = table("matches"), table("balls")
m = m[m["final_winner"].notna()].sort_values("match_seq")
WK = "Wankhede Stadium, Mumbai"
CSK, MI = "Chennai Super Kings", "Mumbai Indians"

w = m[m["venue"] == WK]
bf = b[b["innings"] == 1].groupby("match_id")["batting_team"].first()
chase_wins = sum(bf[mid] != win for mid, win in zip(w["match_id"], w["final_winner"]))

r = get_match_preview("csk", "mi", "wankhede")
d, g, h = r["data"], r["data"]["ground"], r["data"]["head_to_head"]
check("ground: match count", g["matches"] == len(w))
check("ground: chase win %", abs(g["chase_win_pct"] - chase_wins / len(w) * 100) < 0.06)
check("ground: chase + bat-first = 100", abs(g["chase_win_pct"] + g["bat_first_win_pct"] - 100) < 0.11)
check("ground: since-2022 match count", g["since_2022"]["matches"] == len(w[w["year"] >= 2022]))
check("ground: par is a sensible score", 130 < g["par_score"] < 200)

pair = m[m["team1"].isin([CSK, MI]) & m["team2"].isin([CSK, MI])]
check("h2h: meetings = wins added up", h["meetings"] == len(pair) == sum(h["wins"].values()))
check("h2h: CSK wins", h["wins"][CSK] == int((pair["final_winner"] == CSK).sum()))
check("h2h: since-2020 count", h["since_2020"]["meetings"] == len(pair[pair["year"] >= 2020]))
check("h2h: five last meetings, newest last",
      len(h["last_meetings"]) == 5 and h["last_meetings"][-1]["date"] == str(pair["date"].max().date()))

for t in d["teams"]:
    tm = m[(m["team1"] == t["team"]) | (m["team2"] == t["team"])]
    here = tm[tm["venue"] == WK]
    form = "".join("W" if x == t["team"] else "L" for x in tm.tail(5)["final_winner"])
    check(f"{t['team']}: matches and ground record",
          t["matches"] == len(tm) and t["at_ground"]["matches"] == len(here)
          and t["at_ground"]["wins"] == int((here["final_winner"] == t["team"]).sum()))
    check(f"{t['team']}: form string", t["form_last5"] == form)
    check(f"{t['team']}: last 15", (t["wins_last15"], t["of_last15"]) == (int((tm.tail(15)["final_winner"] == t["team"]).sum()), 15))

check("MI is at home, CSK away", [t["ground_status_latest_season"] for t in d["teams"]] == ["away", "home"])
rev = get_match_preview("mi", "csk", "wankhede")["data"]
check("team order does not change the facts", rev["ground"] == g and rev["head_to_head"]["wins"] == h["wins"])
check("chart: one point per season", len(r["chart"]["x"]) == len(r["chart"]["avg_first"]) == len(r["chart"]["matches"]))

dc = get_match_preview("deccan", "mi", "wankhede")
check("defunct team gets a 'last played' warning", any("last played" in x for x in dc["warnings"]))
nm = get_match_preview("kochi", "gujarat lions", "eden gardens")
check("teams that never met", nm["data"]["head_to_head"]["meetings"] == 0 and any("never met" in x for x in nm["warnings"]))

check("same team twice fails", not get_match_preview("csk", "csk", "wankhede")["ok"])
check("ambiguous team fails", not get_match_preview("gujarat", "mi", "wankhede")["ok"])
check("ambiguous ground fails", not get_match_preview("csk", "mi", "mumbai")["ok"])
check("unknown ground fails", not get_match_preview("csk", "mi", "xyzzy")["ok"])

print("\nfailures:", fails)

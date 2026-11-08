"""Rebuild all 15 IPL tables from the raw match JSON files.
Run from the project root:  python pipeline\\build_tables.py
"""
import os, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "ipl_json"
OUT_DIR = ROOT / "data" / "processed"

TEAM_ALIASES = {
    "Delhi Daredevils": "Delhi Capitals",
    "Kings XI Punjab": "Punjab Kings",
    "Royal Challengers Bangalore": "Royal Challengers Bengaluru",
    "Rising Pune Supergiants": "Rising Pune Supergiant",
}

VENUES = {
    "Eden Gardens, Kolkata": ["Eden Gardens", "Eden Gardens, Kolkata"],
    "Wankhede Stadium, Mumbai": ["Wankhede Stadium", "Wankhede Stadium, Mumbai"],
    "M Chinnaswamy Stadium, Bengaluru": ["M Chinnaswamy Stadium", "M Chinnaswamy Stadium, Bengaluru", "M.Chinnaswamy Stadium"],
    "Arun Jaitley Stadium, Delhi": ["Feroz Shah Kotla", "Arun Jaitley Stadium", "Arun Jaitley Stadium, Delhi"],
    "Rajiv Gandhi International Stadium, Hyderabad": ["Rajiv Gandhi International Stadium, Uppal", "Rajiv Gandhi International Stadium, Uppal, Hyderabad", "Rajiv Gandhi International Stadium"],
    "MA Chidambaram Stadium, Chennai": ["MA Chidambaram Stadium, Chepauk", "MA Chidambaram Stadium, Chepauk, Chennai", "MA Chidambaram Stadium"],
    "Sawai Mansingh Stadium, Jaipur": ["Sawai Mansingh Stadium", "Sawai Mansingh Stadium, Jaipur"],
    "PCA IS Bindra Stadium, Mohali": ["Punjab Cricket Association Stadium, Mohali", "Punjab Cricket Association IS Bindra Stadium, Mohali", "Punjab Cricket Association IS Bindra Stadium", "Punjab Cricket Association IS Bindra Stadium, Mohali, Chandigarh"],
    "Narendra Modi Stadium, Ahmedabad": ["Narendra Modi Stadium, Ahmedabad", "Sardar Patel Stadium, Motera"],
    "MCA Stadium, Pune": ["Maharashtra Cricket Association Stadium", "Maharashtra Cricket Association Stadium, Pune", "Subrata Roy Sahara Stadium"],
    "Dr DY Patil Sports Academy, Navi Mumbai": ["Dr DY Patil Sports Academy", "Dr DY Patil Sports Academy, Mumbai"],
    "Brabourne Stadium, Mumbai": ["Brabourne Stadium", "Brabourne Stadium, Mumbai"],
    "Dubai International Cricket Stadium, Dubai": ["Dubai International Cricket Stadium"],
    "Sheikh Zayed Stadium, Abu Dhabi": ["Sheikh Zayed Stadium", "Zayed Cricket Stadium, Abu Dhabi"],
    "Sharjah Cricket Stadium, Sharjah": ["Sharjah Cricket Stadium"],
    "Ekana Cricket Stadium, Lucknow": ["Bharat Ratna Shri Atal Bihari Vajpayee Ekana Cricket Stadium, Lucknow"],
    "ACA-VDCA Stadium, Visakhapatnam": ["Dr. Y.S. Rajasekhara Reddy ACA-VDCA Cricket Stadium", "Dr. Y.S. Rajasekhara Reddy ACA-VDCA Cricket Stadium, Visakhapatnam"],
    "HPCA Stadium, Dharamsala": ["Himachal Pradesh Cricket Association Stadium", "Himachal Pradesh Cricket Association Stadium, Dharamsala"],
    "Maharaja Yadavindra Singh Stadium, Mullanpur": ["Maharaja Yadavindra Singh International Cricket Stadium, Mullanpur", "Maharaja Yadavindra Singh International Cricket Stadium, New Chandigarh"],
    "Kingsmead, Durban": ["Kingsmead"],
    "SuperSport Park, Centurion": ["SuperSport Park"],
    "New Wanderers Stadium, Johannesburg": ["New Wanderers Stadium"],
    "St George's Park, Gqeberha": ["St George's Park"],
    "Newlands, Cape Town": ["Newlands"],
    "De Beers Diamond Oval, Kimberley": ["De Beers Diamond Oval"],
    "Buffalo Park, East London": ["Buffalo Park"],
    "OUTsurance Oval, Bloemfontein": ["OUTsurance Oval"],
    "Saurashtra Cricket Association Stadium, Rajkot": ["Saurashtra Cricket Association Stadium"],
    "Holkar Cricket Stadium, Indore": ["Holkar Cricket Stadium"],
    "JSCA International Stadium Complex, Ranchi": ["JSCA International Stadium Complex"],
    "Barabati Stadium, Cuttack": ["Barabati Stadium"],
    "Shaheed Veer Narayan Singh Stadium, Raipur": ["Shaheed Veer Narayan Singh International Stadium"],
    "Nehru Stadium, Kochi": ["Nehru Stadium"],
    "Barsapara Cricket Stadium, Guwahati": ["Barsapara Cricket Stadium, Guwahati"],
    "Green Park, Kanpur": ["Green Park"],
    "Vidarbha Cricket Association Stadium, Nagpur": ["Vidarbha Cricket Association Stadium, Jamtha"],
}
VENUE_MAP = {v: canon for canon, variants in VENUES.items() for v in variants}

BOWLER_KINDS = {"bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket"}
NOT_OUT_KINDS = {"retired hurt", "retired not out"}


# ------------------------------------------------------------------ extract
def extract(raw_dir):
    balls, wkts, matches, players = [], [], [], []
    files = sorted(f for f in os.listdir(raw_dir) if f.endswith(".json"))
    for fn in files:
        with open(os.path.join(raw_dir, fn), encoding="utf-8") as f:
            m = json.load(f)
        info, mid = m["info"], fn[:-5]
        teams = info.get("teams", [])
        reg = info.get("registry", {}).get("people", {})
        out, toss, ev = info.get("outcome", {}), info.get("toss", {}), info.get("event", {})

        matches.append({
            "match_id": mid, "date": info["dates"][0], "season_raw": info.get("season"),
            "venue": info.get("venue"), "city": info.get("city"),
            "team1": teams[0] if len(teams) > 0 else None,
            "team2": teams[1] if len(teams) > 1 else None,
            "toss_winner": toss.get("winner"), "toss_decision": toss.get("decision"),
            "winner": out.get("winner"), "result": out.get("result"),
            "super_over_winner": out.get("eliminator"),
            "win_by_runs": out.get("by", {}).get("runs"),
            "win_by_wickets": out.get("by", {}).get("wickets"),
            "method": out.get("method"),
            "player_of_match": ", ".join(info.get("player_of_match", [])),
            "event_name": ev.get("name"), "match_number": ev.get("match_number"),
            "stage": ev.get("stage"),
        })
        for team, plist in info.get("players", {}).items():
            for name in plist:
                players.append({"match_id": mid, "team": team, "player": name,
                                "player_id": reg.get(name)})

        inn_no = 0
        for inn in m.get("innings", []):
            if inn.get("super_over"):
                continue
            inn_no += 1
            bat_team = inn["team"]
            bowl_team = next((t for t in teams if t != bat_team), None)
            for od in inn.get("overs", []):
                for ball_no, d in enumerate(od["deliveries"], start=1):
                    r, ex = d["runs"], d.get("extras", {})
                    batter, bowler = d["batter"], d["bowler"]
                    balls.append({
                        "match_id": mid, "innings": inn_no,
                        "batting_team": bat_team, "bowling_team": bowl_team,
                        "over": od["over"], "ball_in_over": ball_no,
                        "batter": batter, "batter_id": reg.get(batter),
                        "bowler": bowler, "bowler_id": reg.get(bowler),
                        "non_striker": d.get("non_striker"),
                        "non_striker_id": reg.get(d.get("non_striker")),
                        "runs_batter": r["batter"], "runs_extras": r["extras"], "runs_total": r["total"],
                        "wides": ex.get("wides", 0), "noballs": ex.get("noballs", 0),
                        "byes": ex.get("byes", 0), "legbyes": ex.get("legbyes", 0),
                        "penalty": ex.get("penalty", 0),
                        "is_wide": "wides" in ex, "is_noball": "noballs" in ex,
                        "is_wicket": "wickets" in d,
                    })
                    for w in d.get("wickets", []):
                        fl = [x.get("name") for x in w.get("fielders", []) if x.get("name")]
                        wkts.append({
                            "match_id": mid, "innings": inn_no,
                            "batting_team": bat_team, "bowling_team": bowl_team,
                            "over": od["over"], "ball_in_over": ball_no,
                            "player_out": w["player_out"], "player_out_id": reg.get(w["player_out"]),
                            "kind": w["kind"], "bowler": bowler, "bowler_id": reg.get(bowler),
                            "fielders": ", ".join(fl), "striker": batter,
                            "non_striker": d.get("non_striker"),
                            "striker_id": reg.get(batter),
                            "non_striker_id": reg.get(d.get("non_striker")),
                            "bowler_wicket": w["kind"] in BOWLER_KINDS,
                            "counts_as_out": w["kind"] not in NOT_OUT_KINDS,
                        })
    return pd.DataFrame(balls), pd.DataFrame(wkts), pd.DataFrame(matches), pd.DataFrame(players)


# ------------------------------------------------------------------ clean
def clean(df_ball, df_wkts, df_match, df_players):
    for c in ["team1", "team2", "toss_winner", "winner", "super_over_winner"]:
        df_match[c] = df_match[c].replace(TEAM_ALIASES)
    for d in (df_ball, df_wkts):
        for c in ["batting_team", "bowling_team"]:
            d[c] = d[c].replace(TEAM_ALIASES)
    df_players["team"] = df_players["team"].replace(TEAM_ALIASES)

    df_match["date"] = pd.to_datetime(df_match["date"])
    df_match["year"] = df_match["date"].dt.year
    df_match["season"] = df_match["year"]
    df_match["season_raw"] = df_match["season_raw"].astype(str)
    df_match["match_number"] = pd.to_numeric(df_match["match_number"], errors="coerce")
    df_match = df_match.sort_values(["date", "match_number", "match_id"]).reset_index(drop=True)
    df_match["match_seq"] = df_match.index + 1

    df_match["venue_raw"] = df_match["venue"]
    df_match["venue"] = df_match["venue_raw"].map(VENUE_MAP)
    bad = df_match.loc[df_match["venue"].isna(), "venue_raw"].unique()
    if len(bad):
        raise ValueError(f"Unmapped venues, add them to VENUES: {list(bad)}")
    df_match["city"] = df_match["venue"].str.split(", ").str[-1]

    df_match["final_winner"] = df_match["winner"].fillna(df_match["super_over_winner"])
    df_match["is_no_result"] = df_match["result"].eq("no result")

    df_ball["is_legal"] = ~(df_ball["is_wide"] | df_ball["is_noball"])
    df_ball["batter_ball_faced"] = ~df_ball["is_wide"]
    df_ball["bowler_runs"] = df_ball["runs_batter"] + df_ball["wides"] + df_ball["noballs"]
    df_ball["is_four"] = (df_ball["runs_batter"] == 4).astype(int)
    df_ball["is_six"] = (df_ball["runs_batter"] == 6).astype(int)
    df_ball["bat_dot"] = (df_ball["batter_ball_faced"] & (df_ball["runs_batter"] == 0)).astype(int)

    ymap = df_match.set_index("match_id")["year"]
    to_phase = lambda o: "powerplay" if o <= 5 else ("middle" if o <= 14 else "death")
    for d in (df_ball, df_wkts):
        d["phase"] = d["over"].map(to_phase)
        d["year"] = d["match_id"].map(ymap)
    df_ball, df_wkts, df_players = canonicalise(df_ball, df_wkts, df_match, df_players)
    return df_ball, df_wkts, df_match, df_players

def canonicalise(df_ball, df_wkts, df_match, df_players):
    pl = (df_players.dropna(subset=["player_id"])
          .merge(df_match[["match_id", "match_seq"]], on="match_id")
          .sort_values("match_seq"))
    canon = pl.groupby("player_id")["player"].last().to_dict()       # latest spelling per id
    played = pl.groupby("player_id")["match_id"].nunique().to_dict()

    by_name = {}
    for pid, name in canon.items():
        by_name.setdefault(name, []).append(pid)
    for name, pids in by_name.items():
        if len(pids) > 1:                                             # same name, different people
            pids.sort(key=lambda p: -played[p])
            for p in pids[1:]:
                canon[p] = f"{name} [{p[:4]}]"
            print("name shared by several ids, tagged:", [canon[p] for p in pids])

    def remap(df, name_col, id_col):
        df[name_col] = df[id_col].map(canon).fillna(df[name_col])

    remap(df_ball, "batter", "batter_id")
    remap(df_ball, "bowler", "bowler_id")
    remap(df_ball, "non_striker", "non_striker_id")
    remap(df_wkts, "player_out", "player_out_id")
    remap(df_wkts, "bowler", "bowler_id")
    remap(df_wkts, "striker", "striker_id")
    remap(df_wkts, "non_striker", "non_striker_id")
    remap(df_players, "player", "player_id")
    return df_ball, df_wkts, df_players


# ------------------------------------------------------------------ batting
def build_batting(df_ball, df_wkts, df_match, df_players):
    bat = (df_ball.groupby(["match_id", "innings", "batting_team", "batter"])
           .agg(runs=("runs_batter", "sum"), balls=("batter_ball_faced", "sum"),
                fours=("is_four", "sum"), sixes=("is_six", "sum")).reset_index())
    outs = (df_wkts[df_wkts["counts_as_out"]]
            .groupby(["match_id", "innings", "batting_team", "player_out"]).size()
            .rename("outs").reset_index().rename(columns={"player_out": "batter"}))
    bat = bat.merge(outs, on=["match_id", "innings", "batting_team", "batter"], how="outer")
    for c in ["runs", "balls", "fours", "sixes", "outs"]:
        bat[c] = bat[c].fillna(0).astype(int)

    bat = bat.merge(df_match[["match_id", "date", "year", "venue", "team1", "team2", "match_seq"]],
                    on="match_id", how="left")
    bat["opposition"] = np.where(bat["batting_team"] == bat["team1"], bat["team2"], bat["team1"])
    bat = bat.drop(columns=["team1", "team2"])
    id_map = df_players.drop_duplicates("player").set_index("player")["player_id"]
    bat["batter_id"] = bat["batter"].map(id_map)
    bat["strike_rate"] = bat["runs"] / bat["balls"].where(bat["balls"] > 0) * 100
    bat = bat.sort_values(["batter", "match_seq", "innings"]).reset_index(drop=True)
    bat["inning_no"] = bat.groupby("batter").cumcount() + 1

    g = bat.groupby("batter")
    for c in ["runs", "balls", "outs"]:
        bat[f"roll_{c}"] = g[c].transform(lambda s: s.rolling(10, min_periods=5).sum())
    bat["roll_sr"] = bat["roll_runs"] / bat["roll_balls"] * 100
    bat["roll_avg"] = bat["roll_runs"] / bat["roll_outs"].where(bat["roll_outs"] > 0)
    return bat


def build_season_batting(bat):
    s = (bat.groupby(["batter", "year"])
         .agg(team=("batting_team", lambda x: x.mode().iat[0]), innings=("match_id", "count"),
              runs=("runs", "sum"), balls=("balls", "sum"), outs=("outs", "sum"),
              fours=("fours", "sum"), sixes=("sixes", "sum"), high_score=("runs", "max"),
              fifties=("runs", lambda x: ((x >= 50) & (x < 100)).sum()),
              hundreds=("runs", lambda x: (x >= 100).sum())).reset_index())
    s["avg"] = s["runs"] / s["outs"].where(s["outs"] > 0)
    s["sr"] = s["runs"] / s["balls"] * 100
    s["runs_per_inn"] = s["runs"] / s["innings"]
    return s


# ------------------------------------------------------------------ bowling
def build_bowling(df_ball, df_wkts, df_match, df_players):
    b = df_ball.copy()
    b["legal"] = b["is_legal"].astype(int)
    b["dot"] = (b["is_legal"] & (b["runs_batter"] == 0)).astype(int)
    bowl = (b.groupby(["match_id", "innings", "bowling_team", "batting_team", "bowler"])
            .agg(balls=("legal", "sum"), runs=("bowler_runs", "sum"), dots=("dot", "sum"),
                 wides=("wides", "sum"), noballs=("noballs", "sum"),
                 fours=("is_four", "sum"), sixes=("is_six", "sum")).reset_index()
            .rename(columns={"bowling_team": "team", "batting_team": "opposition"}))
    wk = (df_wkts[df_wkts["bowler_wicket"]].groupby(["match_id", "innings", "bowler"]).size()
          .rename("wickets").reset_index())
    bowl = bowl.merge(wk, on=["match_id", "innings", "bowler"], how="left")
    bowl["wickets"] = bowl["wickets"].fillna(0).astype(int)
    bowl = bowl.merge(df_match[["match_id", "date", "year", "venue", "match_seq"]], on="match_id", how="left")
    id_map = df_players.drop_duplicates("player").set_index("player")["player_id"]
    bowl["bowler_id"] = bowl["bowler"].map(id_map)
    bowl["economy"] = bowl["runs"] / (bowl["balls"].where(bowl["balls"] > 0) / 6)
    bowl = bowl.sort_values(["bowler", "match_seq", "innings"]).reset_index(drop=True)
    bowl["inning_no"] = bowl.groupby("bowler").cumcount() + 1
    return bowl


def build_season_bowling(bowl):
    s = (bowl.groupby(["bowler", "year"])
         .agg(team=("team", lambda x: x.mode().iat[0]), innings=("match_id", "count"),
              balls=("balls", "sum"), runs=("runs", "sum"), wickets=("wickets", "sum"),
              dots=("dots", "sum"), best_wkts=("wickets", "max"),
              three_w=("wickets", lambda x: (x >= 3).sum()),
              five_w=("wickets", lambda x: (x >= 5).sum())).reset_index())
    s["economy"] = s["runs"] / (s["balls"] / 6)
    s["avg"] = s["runs"] / s["wickets"].where(s["wickets"] > 0)
    s["sr"] = s["balls"] / s["wickets"].where(s["wickets"] > 0)
    return s


# ------------------------------------------------------------------ splits
def build_splits(df_ball, df_wkts, bat):
    bp = (df_ball.groupby(["batter", "year", "phase"])
          .agg(runs=("runs_batter", "sum"), balls=("batter_ball_faced", "sum"),
               fours=("is_four", "sum"), sixes=("is_six", "sum"), dots=("bat_dot", "sum")).reset_index())
    o = (df_wkts[df_wkts["counts_as_out"]].groupby(["player_out", "year", "phase"]).size()
         .rename("outs").reset_index().rename(columns={"player_out": "batter"}))
    bp = bp.merge(o, on=["batter", "year", "phase"], how="outer").fillna(0)
    for c in ["runs", "balls", "fours", "sixes", "dots", "outs"]:
        bp[c] = bp[c].astype(int)
    bp["sr"] = bp["runs"] / bp["balls"].where(bp["balls"] > 0) * 100
    bp["avg"] = bp["runs"] / bp["outs"].where(bp["outs"] > 0)

    wp = (df_ball.groupby(["bowler", "year", "phase"])
          .agg(balls=("is_legal", "sum"), runs=("bowler_runs", "sum")).reset_index())
    w = (df_wkts[df_wkts["bowler_wicket"]].groupby(["bowler", "year", "phase"]).size()
         .rename("wickets").reset_index())
    wp = wp.merge(w, on=["bowler", "year", "phase"], how="left")
    wp["wickets"] = wp["wickets"].fillna(0).astype(int)
    wp["economy"] = wp["runs"] / (wp["balls"].where(wp["balls"] > 0) / 6)

    h = (df_ball.groupby(["batter", "bowler"])
         .agg(runs=("runs_batter", "sum"), balls=("batter_ball_faced", "sum"),
              dots=("bat_dot", "sum"), fours=("is_four", "sum"), sixes=("is_six", "sum")).reset_index())
    ho = (df_wkts[df_wkts["bowler_wicket"]].groupby(["player_out", "bowler"]).size()
          .rename("outs").reset_index().rename(columns={"player_out": "batter"}))
    h = h.merge(ho, on=["batter", "bowler"], how="left")
    h["outs"] = h["outs"].fillna(0).astype(int)
    h["sr"] = h["runs"] / h["balls"].where(h["balls"] > 0) * 100

    def split(key):
        t = (bat.groupby(["batter", key])
             .agg(innings=("match_id", "count"), runs=("runs", "sum"), balls=("balls", "sum"),
                  outs=("outs", "sum"), high_score=("runs", "max")).reset_index())
        t["avg"] = t["runs"] / t["outs"].where(t["outs"] > 0)
        t["sr"] = t["runs"] / t["balls"].where(t["balls"] > 0) * 100
        return t

    return bp, wp, h, split("opposition"), split("venue")


# ------------------------------------------------------------------ careers
def build_career_batting(bat, season):
    d = bat.copy()
    dismissed = d["outs"] > 0
    d["contrib"] = (d["runs"] >= 20) | ((d["runs"] >= 10) & (d["strike_rate"] >= 150))
    d["fail"] = (d["runs"] < 10) & dismissed
    d["fifty_plus"] = d["runs"] >= 50
    d["duck"] = (d["runs"] == 0) & dismissed
    c = d.groupby("batter").agg(
        innings=("runs", "size"), runs=("runs", "sum"), balls=("balls", "sum"),
        outs=("outs", "sum"), high_score=("runs", "max"), median_runs=("runs", "median"),
        contrib_rate=("contrib", "mean"), fail_rate=("fail", "mean"),
        fifty_rate=("fifty_plus", "mean"), duck_rate=("duck", "mean")).reset_index()
    c["avg"] = c["runs"] / c["outs"].where(c["outs"] > 0)
    c["sr"] = c["runs"] / c["balls"] * 100
    c["consistency"] = 100 * (0.6 * c["contrib_rate"] + 0.4 * (1 - c["fail_rate"]))
    s = season.sort_values("year").groupby("batter").agg(
        first_year=("year", "min"), last_year=("year", "max"), seasons=("year", "nunique"),
        seasons_300=("runs", lambda x: (x >= 300).sum()),
        teams=("team", lambda t: ", ".join(dict.fromkeys(t)))).reset_index()
    return c.merge(s, on="batter", how="left")


def build_career_bowling(bowl, bseason):
    t = bowl.groupby("bowler").agg(innings=("balls", "size"), balls=("balls", "sum"),
                                   runs=("runs", "sum"), wickets=("wickets", "sum")).reset_index()
    t["economy"] = t["runs"] / (t["balls"] / 6)
    d = bowl[bowl["balls"] >= 12].copy()
    d["took_wkt"] = d["wickets"] >= 1
    d["expensive"] = d["economy"] >= 10
    r = d.groupby("bowler").agg(spells=("balls", "size"), median_economy=("economy", "median"),
                                wkt_rate=("took_wkt", "mean"), exp_rate=("expensive", "mean")).reset_index()
    c = t.merge(r, on="bowler", how="left")
    c["consistency"] = 100 * (0.5 * c["wkt_rate"] + 0.5 * (1 - c["exp_rate"]))
    s = bseason.sort_values("year").groupby("bowler").agg(
        first_year=("year", "min"), last_year=("year", "max"), seasons=("year", "nunique"),
        teams=("team", lambda x: ", ".join(dict.fromkeys(x)))).reset_index()
    return c.merge(s, on="bowler", how="left")


# ------------------------------------------------------------------ main
def check(label, got, want):
    print(f"{'OK  ' if got == want else 'FAIL'} {label}: {got} (expected {want})")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("extracting...")
    df_ball, df_wkts, df_match, df_players = clean(*extract(RAW_DIR))

    print("building tables...")
    bat = build_batting(df_ball, df_wkts, df_match, df_players)
    season = build_season_batting(bat)
    bowl = build_bowling(df_ball, df_wkts, df_match, df_players)
    bseason = build_season_bowling(bowl)
    bat_phase, bowl_phase, h2h, vs_team, at_venue = build_splits(df_ball, df_wkts, bat)

    tables = {
        "balls": df_ball, "wickets": df_wkts, "matches": df_match, "players": df_players,
        "player_match_batting": bat, "player_season_batting": season,
        "player_match_bowling": bowl, "player_season_bowling": bseason,
        "batting_by_phase": bat_phase, "bowling_by_phase": bowl_phase,
        "batter_vs_bowler": h2h, "batter_vs_team": vs_team, "batter_at_venue": at_venue,
        "career_batting": build_career_batting(bat, season),
        "career_bowling": build_career_bowling(bowl, bseason),
    }
    for name, d in tables.items():
        d.to_parquet(OUT_DIR / f"{name}.parquet", index=False)
        print(f"saved {name:25} {d.shape}")

    cb = tables["career_bowling"].set_index("bowler")
    check("DJ Bravo wickets", int(cb.loc["DJ Bravo", "wickets"]), 183)
    check("SL Malinga wickets", int(cb.loc["SL Malinga", "wickets"]), 170)
    print("date range:", df_match["date"].min().date(), "->", df_match["date"].max().date())


if __name__ == "__main__":
    main()
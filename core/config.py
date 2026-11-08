from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "ipl_json"
DATA_DIR = ROOT / "data" / "processed"
MODEL_DIR = ROOT / "models"

DATA_THROUGH = "IPL 2025"

TABLES = [
    "balls", "wickets", "matches", "players",
    "player_match_batting", "player_season_batting",
    "player_match_bowling", "player_season_bowling",
    "batting_by_phase", "bowling_by_phase",
    "batter_vs_bowler", "batter_vs_team", "batter_at_venue",
    "career_batting", "career_bowling",
]
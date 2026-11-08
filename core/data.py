from functools import lru_cache
import pandas as pd

from core.config import DATA_DIR, TABLES


@lru_cache(maxsize=None)
def table(name: str) -> pd.DataFrame:
    """Load one table, once. Treat the result as read-only: copy it before changing it."""
    if name not in TABLES:
        raise KeyError(f"Unknown table '{name}'. Choose from: {TABLES}")
    path = DATA_DIR / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing. Run: python pipeline\\build_tables.py")
    return pd.read_parquet(path)


def preload() -> dict:
    """Load all 15 tables (used at app start-up so the first question isn't slow)."""
    return {name: table(name) for name in TABLES}
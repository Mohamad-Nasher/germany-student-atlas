"""Loaders for the hand-maintained input files in data/manual/.

Rents and student numbers have no stable public API, so they come from small
CSV files you fill in from the official publications (see data/manual/README.md).
A missing file is not an error: that layer is simply reported as missing.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import MANUAL

SCHEMAS = {
    "rents.csv": ["city", "wg_room_eur", "rent_eur_m2", "period", "source"],
    "students.csv": ["city", "students_total", "students_international", "semester", "source"],
    "sector_official.csv": ["sector", "shortage_score", "employment_change_pct", "source"],
}


def load(name: str, folder: Path | None = None) -> pd.DataFrame | None:
    path = (folder or MANUAL) / name
    if not path.exists():
        return None
    df = pd.read_csv(path, comment="#")
    missing = [c for c in SCHEMAS[name] if c not in df.columns]
    if missing:
        raise ValueError(f"{path} is missing columns: {missing}")
    if df.empty:
        return None
    key = SCHEMAS[name][0]
    if df[key].duplicated().any():
        dupes = sorted(df.loc[df[key].duplicated(), key].unique())
        raise ValueError(f"{path} has duplicate rows for: {dupes}")
    return df

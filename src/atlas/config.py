"""Paths and settings shared by every module."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
MANUAL = ROOT / "data" / "manual"
HISTORY = ROOT / "data" / "history"
OUT = ROOT / "docs" / "data"


def load_settings(path: Path | None = None) -> dict:
    with open(path or CONFIG / "settings.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_cities() -> pd.DataFrame:
    return pd.read_csv(CONFIG / "cities.csv")


def load_sectors() -> pd.DataFrame:
    return pd.read_csv(CONFIG / "sectors.csv")


def monthly_student_income(settings: dict) -> float:
    s = settings["student_income"]
    return s["hourly_wage_eur"] * s["hours_per_week"] * s["weeks_per_month"]

"""Synthetic placeholder data so the map can be previewed before the first real run.

EVERY NUMBER PRODUCED HERE IS INVENTED. Values are drawn from a seeded random
generator and are not estimates of anything. The output is flagged
`"sample": true`, and the map shows a banner for as long as that flag is set.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .build import _layer, publish
from .config import OUT, load_cities, load_sectors
from .sectors import classify


def make(settings: dict, out_dir: Path = OUT, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    cities = load_cities()
    n = len(cities)
    students = rng.integers(8_000, 120_000, n)
    cities["students_total"] = students
    cities["students_international"] = (students * rng.uniform(0.06, 0.28, n)).astype(int)
    cities["wg_room_eur"] = rng.integers(300, 800, n)
    cities["rent_eur_m2"] = np.nan
    jobs = (students / 1000 * rng.uniform(2, 14, n)).astype(int)
    share_en = rng.uniform(0.05, 0.4, n)
    cities["jobs_total"] = jobs
    cities["jobs_en"] = (jobs * share_en).astype(int)
    cities["jobs_de"] = jobs - cities["jobs_en"]
    cities["jobs_unclassified"] = 0
    cities["other_total"] = rng.integers(0, 40, n)
    cities["other_en"] = (cities["other_total"] * 0.7).astype(int)
    cities["other_de"] = cities["other_total"] - cities["other_en"]

    sectors = load_sectors()
    m = len(sectors)
    sectors["stock"] = rng.integers(2_000, 60_000, m)
    sectors["fresh"] = (sectors["stock"] * rng.uniform(0.15, 0.6, m)).astype(int)
    sectors["stock_change"] = rng.uniform(-0.3, 0.3, m)
    sectors["shortage_score"] = rng.uniform(0.5, 2.8, m).round(1)
    sectors["employment_change_pct"] = np.nan
    sector_table = classify(sectors)

    note = "SYNTHETIC placeholder values - not real data"
    layers = {name: _layer("sample", note)
              for name in ("rents", "students", "jobs", "jobs_other", "sectors")}
    return publish(pd.DataFrame(cities), sector_table, layers, settings, out_dir, sample=True)

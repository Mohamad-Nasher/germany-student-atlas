"""Turn raw city figures into the indicators shown on the map."""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_indicators(df: pd.DataFrame, income: float, room_m2: float) -> pd.DataFrame:
    """Add affordability, job-density and competition indicators.

    rent_monthly     WG-room rent; if only EUR/m2 is known, EUR/m2 x room_m2.
    rent_burden      rent_monthly / income of a 20h minimum-wage Werkstudent job.
    jobs_per_1000    Werkstudent postings per 1,000 students.
    intl_per_en_job  international students per English-language posting -
                     the "competition" measure (lower is better).
    score            0-100, mean percentile rank of the three, higher is better.
    """
    df = df.copy()
    for col in ("wg_room_eur", "rent_eur_m2", "listing_median_eur", "students_total",
                "students_international", "jobs_total", "jobs_en", "jobs_de", "other_en"):
        if col not in df:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["rent_monthly"] = (df["listing_median_eur"]
                          .fillna(df["wg_room_eur"])
                          .fillna(df["rent_eur_m2"] * room_m2))
    df["rent_burden"] = df["rent_monthly"] / income
    students = df["students_total"].where(df["students_total"] > 0)
    df["jobs_per_1000"] = df["jobs_total"] / students * 1000
    df["intl_share"] = df["students_international"] / students
    en_jobs = df["jobs_en"].fillna(0) + df["other_en"].fillna(0)
    en_jobs = en_jobs.where(df["jobs_en"].notna() | df["other_en"].notna())
    # +1 keeps cities with zero English postings finite and at the bad end.
    df["intl_per_en_job"] = df["students_international"] / (en_jobs + 1)

    ranks = pd.DataFrame({
        "rent": 1 - df["rent_burden"].rank(pct=True),
        "jobs": df["jobs_per_1000"].rank(pct=True),
        "competition": 1 - df["intl_per_en_job"].rank(pct=True),
    })
    # A score needs all three components; a partial average would not be comparable.
    df["score"] = (ranks.mean(axis=1, skipna=False) * 100).round(1)
    return df


def aggregate_states(df: pd.DataFrame) -> pd.DataFrame:
    """State figures from the cities in this project (not whole-state totals)."""
    def agg(g: pd.DataFrame) -> pd.Series:
        students = g["students_total"].sum(min_count=1)
        weights = g["students_total"].fillna(0)
        rent_ok = g["rent_monthly"].notna() & (weights > 0)
        rent = (np.average(g.loc[rent_ok, "rent_monthly"], weights=weights[rent_ok])
                if rent_ok.any() else g["rent_monthly"].mean())
        jobs = g["jobs_total"].sum(min_count=1)
        intl = g["students_international"].sum(min_count=1)
        return pd.Series({
            "cities": len(g),
            "rent_monthly": rent,
            "students_total": students,
            "students_international": intl,
            "intl_share": intl / students if students else np.nan,
            "jobs_total": jobs,
            "jobs_en": g["jobs_en"].sum(min_count=1),
            "jobs_de": g["jobs_de"].sum(min_count=1),
            "jobs_per_1000": jobs / students * 1000 if students else np.nan,
            "score": g["score"].mean(),
        })
    return df.groupby("state_id").apply(agg, include_groups=False).reset_index()

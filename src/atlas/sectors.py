"""Which occupational fields are hiring, short of people, or shrinking.

Three signals per sector:
  stock        open postings on the federal job board right now;
  fresh_share  share of that stock published in the last 28 days (turnover;
               shown for context, not used for the labels);
  stock_change change in the stock against the oldest snapshot at least three
               weeks old, kept in data/history/sectors.csv.
Official context (shortage score, employment change) is merged from
data/manual/sector_official.csv when you provide it.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from . import jobs_ba
from .http import PoliteSession

MIN_GAP_DAYS = 21
SHORTAGE_THRESHOLD = 2.0   # the federal agency's own cut-off for an "Engpassberuf"
MOVE_THRESHOLD = 0.10      # +/-10 % change in open postings


def snapshot(session: PoliteSession, sectors: pd.DataFrame, fresh_days: int) -> pd.DataFrame:
    """Open postings per sector, in two requests.

    The job board returns a count for every occupational field alongside any
    search, so one request gives the whole stock and a second (restricted to
    postings published in the last `fresh_days`) gives the new ones. A sector
    is the sum of the fields listed for it in config/sectors.csv.
    """
    stock = jobs_ba.facet(session, "berufsfeld", angebotsart=1)
    fresh = jobs_ba.facet(session, "berufsfeld", angebotsart=1, veroeffentlichtseit=fresh_days)
    rows, unknown = [], []
    for row in sectors.itertuples():
        fields = [f.strip() for f in row.berufsfeld.split("|")]
        unknown += [f for f in fields if f not in stock]
        rows.append({"sector": row.sector,
                     "stock": sum(stock.get(f, 0) for f in fields),
                     "fresh": sum(fresh.get(f, 0) for f in fields)})
    if unknown:
        raise ValueError(f"occupational fields not known to the job board: {unknown}")
    return pd.DataFrame(rows)


def append_history(snap: pd.DataFrame, path: Path, today: date | None = None) -> pd.DataFrame:
    today = today or date.today()
    snap = snap.assign(date=today.isoformat())
    if path.exists():
        hist = pd.read_csv(path)
        hist = hist[hist["date"] != today.isoformat()]  # re-runs replace today's rows
        hist = pd.concat([hist, snap], ignore_index=True)
    else:
        hist = snap
    hist[["date", "sector", "stock", "fresh"]].to_csv(path, index=False)
    return hist


def stock_change(hist: pd.DataFrame, today: date | None = None) -> pd.Series:
    """Relative change in stock versus the most recent snapshot >= MIN_GAP_DAYS old."""
    today = today or date.today()
    cutoff = (today - timedelta(days=MIN_GAP_DAYS)).isoformat()
    now = hist[hist["date"] == hist["date"].max()].set_index("sector")["stock"]
    old = hist[hist["date"] <= cutoff]
    if old.empty:
        return pd.Series(dtype=float)
    base = old[old["date"] == old["date"].max()].set_index("sector")["stock"]
    base = base[base > 0]
    return ((now - base) / base).dropna()


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """Label each sector: shortage, booming, struggling, stable or pending.

    Booming / struggling need a trend, i.e. stock_change from two snapshots at
    least MIN_GAP_DAYS apart. Until then the sector is "pending": the share of
    new postings alone cannot tell growth from fast turnover, and a low share
    is typical of hard-to-fill shortage occupations, so it is shown but not
    turned into a verdict.
    """
    df = df.copy()
    df["fresh_share"] = (df["fresh"] / df["stock"]).where(df["stock"] > 0)
    labels, basis = [], []
    for row in df.itertuples():
        change = getattr(row, "stock_change", None)
        score = getattr(row, "shortage_score", None)
        if pd.notna(change):
            momentum = ("booming" if change > MOVE_THRESHOLD
                        else "struggling" if change < -MOVE_THRESHOLD else "stable")
            used = "stock_change"
        else:
            momentum, used = "pending", "none"
        if pd.notna(score) and score >= SHORTAGE_THRESHOLD and momentum != "struggling":
            labels.append("shortage")
            used = "shortage_score" if used == "none" else used
        else:
            labels.append(momentum)
        basis.append(used)
    df["status"], df["basis"] = labels, basis
    return df


def build(snap: pd.DataFrame, hist: pd.DataFrame, sectors: pd.DataFrame,
          official: pd.DataFrame | None, today: date | None = None) -> pd.DataFrame:
    df = sectors.merge(snap, on="sector", how="left")
    df["stock_change"] = df["sector"].map(stock_change(hist, today))
    if official is not None:
        df = df.merge(official, on="sector", how="left")
    for col in ("shortage_score", "employment_change_pct"):
        if col not in df:
            df[col] = pd.NA
    return classify(df)

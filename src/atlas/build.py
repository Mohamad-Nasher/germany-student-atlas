"""Run every source and write the JSON files the map reads."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from . import affordability, jobs_arbeitnow, jobs_ba, listings, manual, sectors
from .config import HISTORY, MANUAL, OUT, load_cities, load_sectors, monthly_student_income
from .http import PoliteSession

CITY_FIELDS = [
    "city", "state_id", "lat", "lon", "rent_monthly", "rent_burden", "rent_eur_m2",
    "wg_room_eur", "listings_n", "students_total", "students_international", "intl_share",
    "jobs_total", "jobs_en", "jobs_de", "jobs_unclassified", "other_total", "other_en",
    "other_de", "jobs_per_1000", "intl_per_en_job", "score",
]


def _clean(value):
    """JSON has no NaN; numpy scalars are not serialisable."""
    if value is None or value is pd.NA:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        return None if math.isnan(value) else round(value, 4)
    return value


def records(df: pd.DataFrame, fields: list[str] | None = None) -> list[dict]:
    cols = [c for c in (fields or df.columns) if c in df.columns]
    return [{c: _clean(v) for c, v in zip(cols, row, strict=True)}
            for row in df[cols].itertuples(index=False, name=None)]


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, allow_nan=False),
                    encoding="utf-8")


def _layer(status: str, detail: str = "", **extra) -> dict:
    return {"status": status, "detail": detail, **extra}


def _distinct(series: pd.Series) -> str:
    return "; ".join(sorted(set(series.dropna().astype(str))))


def fetch_jobs(session: PoliteSession, cities: pd.DataFrame, settings: dict, log=print):
    rows, failed = [], []
    for city in cities["city"]:
        try:
            rows.append({"city": city, **jobs_ba.werkstudent_jobs(session, city, settings)})
        except Exception as exc:  # one bad city must not sink the run
            failed.append(city)
            log(f"  jobs: {city} failed ({exc})")
    if len(failed) > len(cities) / 4:
        raise RuntimeError(f"job search failed for {len(failed)} of {len(cities)} cities")
    detail = "Bundesagentur für Arbeit job board"
    if failed:
        detail += f"; no data for {', '.join(failed)}"
    return pd.DataFrame(rows), detail


def fetch_listings(session: PoliteSession, cities: pd.DataFrame, settings: dict, log=print):
    sources = settings.get("listing_sources") or []
    if not sources:
        return None
    rows = []
    for city in cities["city"]:
        found: list[dict] = []
        for source in sources:
            try:
                found.extend(listings.scrape_city(session, source, city))
            except PermissionError:
                raise
            except Exception as exc:
                log(f"  listings: {source.get('name')} / {city} failed ({exc})")
        summary = listings.summarise(found)
        # A median of a handful of adverts is noise; require a minimum sample.
        if summary["listings_n"] < 20:
            summary["listing_median_eur"] = summary["listing_median_eur_m2"] = None
        rows.append({"city": city, **summary})
    return pd.DataFrame(rows)


def build(settings: dict, *, offline: bool = False, session: PoliteSession | None = None,
          manual_dir: Path = MANUAL, out_dir: Path = OUT, history_dir: Path = HISTORY,
          today: date | None = None, log=print) -> dict:
    today = today or date.today()
    cities = load_cities()
    sector_cfg = load_sectors()
    layers: dict[str, dict] = {}
    session = session or PoliteSession.from_settings(settings)

    # --- hand-maintained official figures -------------------------------------------------
    rents = manual.load("rents.csv", manual_dir)
    if rents is not None:
        cities = cities.merge(rents[["city", "wg_room_eur", "rent_eur_m2"]], on="city",
                              how="left")
        layers["rents"] = _layer("manual", _distinct(rents["source"]),
                                 period=_distinct(rents["period"]))
    else:
        layers["rents"] = _layer("missing", "no rows yet in data/manual/rents.csv")

    students = manual.load("students.csv", manual_dir)
    if students is not None:
        cities = cities.merge(students[["city", "students_total", "students_international"]],
                              on="city", how="left")
        layers["students"] = _layer("manual", _distinct(students["source"]),
                                    period=_distinct(students["semester"]))
    else:
        layers["students"] = _layer("missing", "no rows yet in data/manual/students.csv")

    # --- live sources ----------------------------------------------------------------------
    sector_table = None
    if offline:
        for name in ("jobs", "jobs_other", "sectors"):
            layers[name] = _layer("missing", "skipped (offline build)")
    else:
        log("Fetching Werkstudent postings ...")
        try:
            jobs, detail = fetch_jobs(session, cities, settings, log)
            cities = cities.merge(jobs, on="city", how="left")
            layers["jobs"] = _layer("live", detail)
        except Exception as exc:
            layers["jobs"] = _layer("error", str(exc))

        log("Fetching Arbeitnow postings ...")
        try:
            rows = jobs_arbeitnow.fetch(session)
            other = pd.DataFrame.from_dict(
                jobs_arbeitnow.student_jobs_by_city(rows, list(cities["city"])), orient="index")
            cities = cities.merge(other, left_on="city", right_index=True, how="left")
            layers["jobs_other"] = _layer("live", f"Arbeitnow, {len(rows)} postings scanned")
        except Exception as exc:
            layers["jobs_other"] = _layer("error", str(exc))

        try:
            scraped = fetch_listings(session, cities, settings, log)
            if scraped is not None:
                cities = cities.merge(scraped, on="city", how="left")
                used = int(scraped["listing_median_eur"].notna().sum())
                names = ", ".join(s["name"] for s in settings["listing_sources"])
                layers["listings"] = _layer("live", f"{names}; medians for {used} cities")
        except Exception as exc:
            layers["listings"] = _layer("error", str(exc))

        log("Fetching sector snapshot ...")
        try:
            snap = sectors.snapshot(session, sector_cfg, settings["jobs"]["fresh_days"])
            history_dir.mkdir(parents=True, exist_ok=True)
            hist = sectors.append_history(snap, history_dir / "sectors.csv", today)
            official = manual.load("sector_official.csv", manual_dir)
            sector_table = sectors.build(snap, hist, sector_cfg, official, today)
            layers["sectors"] = _layer(
                "live", "open postings by occupational field, Bundesagentur für Arbeit"
                + ("; official shortage scores merged" if official is not None else ""))
        except Exception as exc:
            layers["sectors"] = _layer("error", str(exc))

    return publish(cities, sector_table, layers, settings, out_dir, sample=False)


def publish(cities: pd.DataFrame, sector_table: pd.DataFrame | None, layers: dict,
            settings: dict, out_dir: Path, *, sample: bool) -> dict:
    income = monthly_student_income(settings)
    table = affordability.add_indicators(cities, income, settings["rent"]["reference_room_m2"])
    states = affordability.aggregate_states(table)
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sample": sample,
        "student_income_eur": round(income, 2),
        "assumptions": settings["student_income"] | settings["rent"],
        "layers": layers,
    }
    write_json(out_dir / "cities.json", records(table, CITY_FIELDS))
    write_json(out_dir / "states.json", records(states))
    write_json(out_dir / "sectors.json", [] if sector_table is None else records(sector_table))
    write_json(out_dir / "meta.json", meta)
    return meta

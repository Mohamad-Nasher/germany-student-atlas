"""Open positions from the Bundesagentur für Arbeit job board.

The agency runs Germany's largest vacancy database. Its search endpoint is the
one behind arbeitsagentur.de/jobsuche; the community documentation lives at
https://github.com/bundesAPI/jobsuche-api. It needs only a public client id.
"""

from __future__ import annotations

from .http import PoliteSession
from .language import classify

URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
HEADERS = {"X-API-Key": "jobboerse-jobsuche"}
PAGE_SIZE = 100


def search(session: PoliteSession, **params) -> dict:
    params.setdefault("angebotsart", 1)  # 1 = regular employment
    return session.get(URL, params=params, headers=HEADERS).json()


def count(session: PoliteSession, **params) -> int:
    """Number of postings matching a query, without downloading them."""
    return int(search(session, size=1, page=1, **params).get("maxErgebnisse") or 0)


def parse_postings(payload: dict) -> list[dict]:
    rows = []
    for item in payload.get("stellenangebote") or []:
        place = item.get("arbeitsort") or {}
        rows.append({
            "id": item.get("refnr"),
            "title": item.get("titel") or item.get("beruf") or "",
            "employer": item.get("arbeitgeber"),
            "city": place.get("ort"),
            "published": item.get("aktuelleVeroeffentlichungsdatum"),
        })
    return rows


def werkstudent_jobs(session: PoliteSession, city: str, settings: dict) -> dict:
    """Werkstudent postings around one city, split by posting language.

    The API reports the total number of hits but returns postings in pages, so
    the language split is measured on a sample (up to max_pages_per_query pages
    per search term) and scaled to the total.
    """
    cfg = settings["jobs"]
    seen: dict[str, dict] = {}
    reported_total = 0
    downloaded = 0
    for term in cfg["search_terms"]:
        for page in range(1, cfg["max_pages_per_query"] + 1):
            payload = search(session, was=term, wo=city, umkreis=cfg["radius_km"],
                             size=PAGE_SIZE, page=page)
            if page == 1:
                reported_total += int(payload.get("maxErgebnisse") or 0)
            postings = parse_postings(payload)
            downloaded += len(postings)
            for p in postings:
                if p["id"]:
                    seen.setdefault(p["id"], p)
            if len(postings) < PAGE_SIZE:
                break
    return summarise(list(seen.values()), reported_total, downloaded)


def summarise(postings: list[dict], reported_total: int, downloaded: int) -> dict:
    """Scale the language split of the sampled postings to the estimated total."""
    sampled = len(postings)
    duplicates = downloaded - sampled  # postings matched by more than one term
    total = max(sampled, reported_total - duplicates)
    labels = [classify(p["title"]) for p in postings]
    en, de = labels.count("en"), labels.count("de")
    scale = total / sampled if sampled else 0
    return {
        "jobs_total": total,
        "jobs_en": round(en * scale),
        "jobs_de": round(de * scale),
        "jobs_unclassified": total - round(en * scale) - round(de * scale),
        "jobs_sampled": sampled,
    }

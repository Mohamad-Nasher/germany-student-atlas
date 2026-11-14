"""Open positions from the Bundesagentur für Arbeit job board.

The agency runs Germany's largest vacancy database. Its search endpoint is the
one behind arbeitsagentur.de/jobsuche; the community documentation lives at
https://github.com/bundesAPI/jobsuche-api. It needs only a public client id.

Response shape (checked against the live service, November 2026):
  ergebnisliste   list of postings (stellenangebotsTitel, referenznummer, firma,
                  stellenlokationen[].adresse.ort, datumErsteVeroeffentlichung)
  maxErgebnisse   total number of hits
  facetten        counts per filter value, e.g. facetten.berufsfeld.counts
"""

from __future__ import annotations

import re

from .http import PoliteSession
from .language import classify

URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
HEADERS = {"X-API-Key": "jobboerse-jobsuche"}
PAGE_SIZE = 100
# The free-text search also returns ordinary internships and jobs that merely
# mention students, so postings are kept only if the title says what they are.
STUDENT_TITLE = re.compile(
    r"werkstudent|working[\s-]*student|studentische|student(?:ische)?\s*(?:aushilfe|hilfskraft)"
    r"|student assistant|student job|studentenjob", re.I)


def search(session: PoliteSession, **params) -> dict:
    return session.get(URL, params=params, headers=HEADERS).json()


def count(session: PoliteSession, **params) -> int:
    """Number of postings matching a query, without downloading them."""
    return int(search(session, size=1, page=1, **params).get("maxErgebnisse") or 0)


def facet(session: PoliteSession, name: str, **params) -> dict[str, int]:
    """Counts per value of one filter (e.g. 'berufsfeld') for a query."""
    payload = search(session, size=1, page=1, **params)
    counts = ((payload.get("facetten") or {}).get(name) or {}).get("counts")
    if not counts:
        raise ValueError(f"the job board returned no '{name}' breakdown")
    return {key: int(value) for key, value in counts.items()}


def parse_postings(payload: dict) -> list[dict]:
    rows = []
    for item in payload.get("ergebnisliste") or []:
        places = item.get("stellenlokationen") or [{}]
        rows.append({
            "id": item.get("referenznummer"),
            "title": item.get("stellenangebotsTitel") or item.get("hauptberuf") or "",
            "employer": item.get("firma"),
            "city": (places[0].get("adresse") or {}).get("ort"),
            "published": item.get("datumErsteVeroeffentlichung"),
        })
    return rows


def werkstudent_jobs(session: PoliteSession, city: str, settings: dict) -> dict:
    """Werkstudent postings around one city, split by posting language.

    The API reports the total number of hits but returns postings in pages, so
    the title filter and the language split are measured on a sample (up to
    max_pages_per_query pages per search term) and scaled to the total.
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
    """Scale the sampled student postings and their language split to the total."""
    sampled = len(postings)
    duplicates = downloaded - sampled  # postings matched by more than one term
    hits = max(sampled, reported_total - duplicates)
    scale = hits / sampled if sampled else 0
    student = [p for p in postings if STUDENT_TITLE.search(p["title"])]
    labels = [classify(p["title"]) for p in student]
    total = round(len(student) * scale)
    en, de = round(labels.count("en") * scale), round(labels.count("de") * scale)
    return {
        "jobs_total": total,
        "jobs_en": en,
        "jobs_de": de,
        "jobs_unclassified": max(0, total - en - de),
        "jobs_sampled": sampled,
    }

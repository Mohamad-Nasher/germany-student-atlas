"""Student jobs from Arbeitnow, a job board with a free public API.

Arbeitnow aggregates postings from company applicant-tracking systems and is
heavy on English-language roles, which the federal job board under-represents.
API: https://www.arbeitnow.com/api/job-board-api (paginated JSON, no key).
"""

from __future__ import annotations

import re

from .http import PoliteSession
from .language import classify

URL = "https://www.arbeitnow.com/api/job-board-api"
_STUDENT = re.compile(r"werkstudent|working student|student assistant|studentische", re.I)
_TAGS = re.compile(r"<[^>]+>")


def fetch(session: PoliteSession, max_pages: int = 10) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        payload = session.get(URL, params={"page": page}).json()
        data = payload.get("data") or []
        rows.extend(data)
        if not data or not (payload.get("links") or {}).get("next"):
            break
    return rows


def student_jobs_by_city(rows: list[dict], cities: list[str]) -> dict[str, dict]:
    """Count student postings per city, split by language."""
    out = {c: {"other_total": 0, "other_en": 0, "other_de": 0} for c in cities}
    # Match on the first word of the city so "Frankfurt am Main" finds "Frankfurt".
    keys = {c: c.split(" ")[0].lower() for c in cities}
    for row in rows:
        title = row.get("title") or ""
        if not _STUDENT.search(title):
            continue
        location = (row.get("location") or "").lower()
        text = title + " " + _TAGS.sub(" ", row.get("description") or "")[:1500]
        lang = classify(text)
        for city, key in keys.items():
            if key in location:
                out[city]["other_total"] += 1
                if lang in ("en", "de"):
                    out[city][f"other_{lang}"] += 1
                break
    return out

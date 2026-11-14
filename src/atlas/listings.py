"""Asking rents from listing sites, for sites that permit automated access.

This scraper is generic and config-driven: a source is a URL template plus CSS
selectors (see docs/DATA_SOURCES.md). It ships with NO sources configured.

Guard rails, enforced in code:
  * a source must carry `terms_checked: true` - you confirm you read its terms;
  * every URL is checked against the site's robots.txt and skipped if disallowed;
  * requests are rate-limited and identified by the project User-Agent;
  * a block (403/429/captcha page) stops the source - it is never worked around.
"""

from __future__ import annotations

import re
import statistics
import unicodedata

from bs4 import BeautifulSoup

from .http import PoliteSession, RobotsDisallowed

_NUMBER = re.compile(r"\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?")


def slugify(city: str) -> str:
    text = city.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def parse_number(text: str | None) -> float | None:
    """Read a German-formatted number: '1.250,50 €' -> 1250.5, '18 m²' -> 18.0."""
    if not text:
        return None
    match = _NUMBER.search(text)
    if not match:
        return None
    raw = match.group(0).replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):
        raw = raw.replace(".", "")
    return float(raw)


def parse_listings(html: str, source: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for item in soup.select(source["item_selector"]):
        price_el = item.select_one(source["price_selector"])
        size_el = item.select_one(source["size_selector"]) if source.get("size_selector") else None
        price = parse_number(price_el.get_text(" ", strip=True) if price_el else None)
        size = parse_number(size_el.get_text(" ", strip=True) if size_el else None)
        # Drop obvious parsing accidents rather than let them move a median.
        if price is None or not 100 <= price <= 5000:
            continue
        if size is not None and not 6 <= size <= 250:
            size = None
        rows.append({"price_eur": price, "size_m2": size})
    return rows


def scrape_city(session: PoliteSession, source: dict, city: str) -> list[dict]:
    if not source.get("terms_checked"):
        raise PermissionError(
            f"Listing source '{source.get('name')}' is missing `terms_checked: true`. "
            "Read the site's terms of use first; many portals forbid automated access."
        )
    rows: list[dict] = []
    for page in range(1, int(source.get("max_pages", 1)) + 1):
        url = source["url_template"].format(city=city, city_slug=slugify(city), page=page)
        try:
            html = session.get(url, respect_robots=True).text
        except RobotsDisallowed:
            break
        found = parse_listings(html, source)
        if not found:
            break
        rows.extend(found)
    return rows


def summarise(rows: list[dict]) -> dict:
    """Median asking price and median EUR/m2 for one city."""
    prices = [r["price_eur"] for r in rows]
    per_m2 = [r["price_eur"] / r["size_m2"] for r in rows if r["size_m2"]]
    return {
        "listings_n": len(rows),
        "listing_median_eur": round(statistics.median(prices), 1) if prices else None,
        "listing_median_eur_m2": round(statistics.median(per_m2), 2) if per_m2 else None,
    }

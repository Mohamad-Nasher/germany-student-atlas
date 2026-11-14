# Data sources, legal notes and how to add a listing source

## What is fetched automatically

| Layer | Source | Access |
|---|---|---|
| Werkstudent postings, by city and language | Bundesagentur für Arbeit job board | public search endpoint, public client id ([community docs](https://github.com/bundesAPI/jobsuche-api)) |
| Student jobs on other boards | [Arbeitnow](https://www.arbeitnow.com/api/job-board-api) | free public JSON API |
| Sector hiring (open postings, share new in 28 days) | Bundesagentur für Arbeit job board | as above |

## What you supply

Rents, student numbers and official shortage scores: see `data/manual/README.md`.

## Why the large rental portals are not scraped

The original idea for this project was to scrape every apartment listing. The
portals that carry most German listings (ImmoScout24, Immowelt, WG-Gesucht,
Kleinanzeigen) state in their terms of use that automated retrieval is not
allowed, and they run bot detection to enforce it. This project does not work
around that: no captcha solving, no rotating IPs or fake browser identities.

Instead the rent layer uses published figures (which are themselves computed
from listings by the Moses Mendelssohn Institut together with WG-Gesucht), and
the repository contains a generic scraper you can point at a site that does
allow it, or for which you have permission.

German copyright law has a text-and-data-mining exception for non-commercial
scientific research (§ 60d UrhG). Whether it covers your use, and how it
interacts with a site's terms, is a legal question; ask your university's
legal or library service before relying on it.

## Adding a listing source

Add an entry under `listing_sources` in `config/settings.yaml`:

```yaml
listing_sources:
  - name: my-source
    terms_checked: true          # you confirm you read the terms of use
    url_template: "https://example.org/rooms/{city_slug}?page={page}"
    max_pages: 3
    item_selector: "article.listing"   # one element per advert
    price_selector: ".price"           # text like "450 €"
    size_selector: ".size"             # optional, text like "18 m²"
```

`{city}` is the name from `config/cities.csv`, `{city_slug}` its lower-case
ASCII form (`Düsseldorf` → `duesseldorf`). The scraper checks the site's
`robots.txt` before each page and stops if the path is disallowed; it waits
`request_delay_seconds` between requests; and a city's median replaces the
manual figure only when at least 20 adverts were parsed.

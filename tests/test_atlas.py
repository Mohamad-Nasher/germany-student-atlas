import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from atlas import affordability, jobs_arbeitnow, jobs_ba, listings, manual, sectors
from atlas.build import build
from atlas.config import load_cities, load_sectors, load_settings, monthly_student_income
from atlas.http import PoliteSession, RobotsDisallowed
from atlas.language import classify

FIX = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, payload=None, text="", status=200):
        self._payload, self.text, self.status_code = payload, text, status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code), response=self)


class FakeHTTP:
    """Stands in for requests.Session; routes by URL substring."""

    def __init__(self, routes):
        self.routes, self.calls, self.headers = routes, [], {}

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params or {}))
        for key, handler in self.routes.items():
            if key in url:
                return handler(params or {}) if callable(handler) else handler
        return FakeResponse(status=404)


def polite(routes):
    http = FakeHTTP(routes)
    return PoliteSession("test-agent", delay=0, sleep=lambda s: None, session=http), http


# --- language ------------------------------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("Werkstudent (m/w/d) im Bereich Controlling", "de"),
    ("Werkstudentin für den Verkauf", "de"),
    ("Working Student Data Engineering (f/m/x)", "en"),
    ("Working Student - Sales Operations", "en"),
    ("(m/w/d)", "unknown"),
    ("", "unknown"),
    (None, "unknown"),
])
def test_classify(title, expected):
    assert classify(title) == expected


# --- federal job board ---------------------------------------------------------------------

def test_parse_postings():
    rows = jobs_ba.parse_postings(fixture("ba_search.json"))
    assert [r["city"] for r in rows] == ["Dortmund"] * 4
    assert rows[1]["title"].startswith("Working Student") and rows[0]["employer"] == "Muster GmbH"


def test_summarise_keeps_only_student_titles_and_scales():
    rows = jobs_ba.parse_postings(fixture("ba_search.json"))
    # 4 postings sampled out of a reported 40 (x10); the plain internship is dropped.
    out = jobs_ba.summarise(rows, reported_total=40, downloaded=4)
    assert out == {"jobs_total": 30, "jobs_en": 10, "jobs_de": 20,
                   "jobs_unclassified": 0, "jobs_sampled": 4}


def test_summarise_removes_cross_term_duplicates():
    rows = jobs_ba.parse_postings(fixture("ba_search.json"))
    # Both search terms returned the same 4 postings: 8 downloaded, 4 unique.
    assert jobs_ba.summarise(rows, reported_total=8, downloaded=8)["jobs_total"] == 3


def test_werkstudent_jobs_sends_expected_query():
    session, http = polite({"arbeitsagentur": FakeResponse(fixture("ba_search.json"))})
    out = jobs_ba.werkstudent_jobs(session, "Dortmund", load_settings())
    assert out["jobs_total"] == 3 and out["jobs_en"] == 1 and out["jobs_de"] == 2
    url, params = http.calls[0]
    assert url.endswith("/pc/v6/jobs")
    assert params["wo"] == "Dortmund" and params["was"] == "Werkstudent"
    assert params["umkreis"] == 15 and "angebotsart" not in params


def test_facet():
    session, _ = polite({"arbeitsagentur": FakeResponse(fixture("ba_search.json"))})
    assert jobs_ba.facet(session, "berufsfeld") == {"Informatik": 5, "Werbung und Marketing": 7}
    with pytest.raises(ValueError):
        jobs_ba.facet(session, "nonexistent")


# --- arbeitnow -----------------------------------------------------------------------------

def test_arbeitnow_counts_only_student_roles_per_city():
    rows = fixture("arbeitnow.json")["data"]
    out = jobs_arbeitnow.student_jobs_by_city(rows, ["Berlin", "Frankfurt am Main", "Dortmund"])
    assert out["Berlin"] == {"other_total": 1, "other_en": 1, "other_de": 0}
    assert out["Frankfurt am Main"] == {"other_total": 1, "other_en": 0, "other_de": 1}
    assert out["Dortmund"]["other_total"] == 0


# --- listings ------------------------------------------------------------------------------

SOURCE = {"name": "demo", "url_template": "https://rooms.example/{city_slug}?p={page}",
          "item_selector": "article.ad", "price_selector": ".price", "size_selector": ".size",
          "max_pages": 1, "terms_checked": True}


@pytest.mark.parametrize("text,expected", [
    ("450 €", 450.0), ("1.250,50 €", 1250.5), ("1250", 1250.0), ("18,5 m²", 18.5),
    ("1.250 €", 1250.0), ("7.5", 7.5), ("auf Anfrage", None), (None, None),
])
def test_parse_number(text, expected):
    assert listings.parse_number(text) == expected


def test_slugify():
    assert listings.slugify("Halle (Saale)") == "halle-saale"
    assert listings.slugify("Düsseldorf") == "duesseldorf"


def test_parse_listings_and_summary():
    rows = listings.parse_listings((FIX / "listings.html").read_text(encoding="utf-8"), SOURCE)
    assert len(rows) == 3  # the advert without a price is dropped
    summary = listings.summarise(rows)
    assert summary["listings_n"] == 3 and summary["listing_median_eur"] == 620.0
    assert summary["listing_median_eur_m2"] == pytest.approx((25 + 1250.5 / 52.5) / 2, abs=0.01)


def test_scrape_requires_terms_confirmation():
    session, _ = polite({})
    with pytest.raises(PermissionError):
        listings.scrape_city(session, {**SOURCE, "terms_checked": False}, "Dortmund")


def test_scrape_stops_when_robots_disallows():
    session, http = polite({
        "robots.txt": FakeResponse(text="User-agent: *\nDisallow: /"),
        "rooms.example": FakeResponse(text=(FIX / "listings.html").read_text(encoding="utf-8")),
    })
    assert listings.scrape_city(session, SOURCE, "Dortmund") == []
    assert all("robots.txt" in url for url, _ in http.calls)  # the page was never requested
    with pytest.raises(RobotsDisallowed):
        session.get("https://rooms.example/x", respect_robots=True)


def test_scrape_when_robots_allows():
    session, _ = polite({
        "robots.txt": FakeResponse(text="User-agent: *\nAllow: /"),
        "rooms.example": FakeResponse(text=(FIX / "listings.html").read_text(encoding="utf-8")),
    })
    assert len(listings.scrape_city(session, SOURCE, "Dortmund")) == 3


# --- indicators ----------------------------------------------------------------------------

def test_indicators():
    df = pd.DataFrame({
        "city": ["A", "B", "C"], "state_id": ["DE-NW", "DE-NW", "DE-BY"],
        "wg_room_eur": [400, None, 800], "rent_eur_m2": [None, 15, None],
        "students_total": [10000, 20000, 50000],
        "students_international": [1000, 4000, 5000],
        "jobs_total": [100, 100, 100], "jobs_en": [9, 0, 49], "jobs_de": [91, 100, 51],
    })
    out = affordability.add_indicators(df, income=1000, room_m2=20).set_index("city")
    assert out.loc["A", "rent_burden"] == pytest.approx(0.4)
    assert out.loc["B", "rent_monthly"] == pytest.approx(300)  # 15 EUR/m2 x 20 m2
    assert out.loc["A", "jobs_per_1000"] == pytest.approx(10)
    assert out.loc["B", "intl_per_en_job"] == pytest.approx(4000)  # zero English postings
    assert out.loc["C", "intl_per_en_job"] == pytest.approx(100)
    assert out["score"].between(0, 100).all()
    states = affordability.aggregate_states(out.reset_index()).set_index("state_id")
    # student-weighted rent: (400*10000 + 300*20000) / 30000
    assert states.loc["DE-NW", "rent_monthly"] == pytest.approx(333.33, abs=0.01)
    assert states.loc["DE-NW", "jobs_total"] == 200


def test_score_is_missing_when_a_component_is_missing():
    df = pd.DataFrame({"city": ["A", "B"], "state_id": ["DE-NW"] * 2,
                       "wg_room_eur": [400, 500]})
    out = affordability.add_indicators(df, income=1000, room_m2=20)
    assert out["score"].isna().all() and out["rent_burden"].notna().all()


def test_student_income_from_settings():
    assert monthly_student_income(load_settings()) == pytest.approx(13.90 * 20 * 4.33)


# --- sectors -------------------------------------------------------------------------------

def test_sector_history_and_change(tmp_path):
    path = tmp_path / "sectors.csv"
    cfg = pd.DataFrame({"sector": ["it", "metal", "care"], "label_en": ["IT", "Metal", "Care"],
                        "berufsfeld": ["a", "b", "c"]})
    old = pd.DataFrame({"sector": ["it", "metal", "care"], "stock": [1000, 1000, 1000],
                        "fresh": [300, 300, 300]})
    new = pd.DataFrame({"sector": ["it", "metal", "care"], "stock": [1200, 800, 1020],
                        "fresh": [500, 100, 300]})
    sectors.append_history(old, path, date(2026, 10, 1))
    hist = sectors.append_history(new, path, date(2026, 11, 1))
    hist = sectors.append_history(new, path, date(2026, 11, 1))  # re-run: no duplicates
    assert len(hist) == 6
    official = pd.DataFrame({"sector": ["care"], "shortage_score": [2.5],
                             "employment_change_pct": [1.0]})
    out = sectors.build(new, hist, cfg, official, date(2026, 11, 1)).set_index("sector")
    assert out.loc["it", "stock_change"] == pytest.approx(0.2)
    assert list(out["status"]) == ["booming", "struggling", "shortage"]
    assert set(out["basis"]) == {"stock_change"}


def test_sector_is_pending_without_history(tmp_path):
    cfg = pd.DataFrame({"sector": ["a", "b"], "label_en": list("AB"), "berufsfeld": list("ab")})
    snap = pd.DataFrame({"sector": ["a", "b"], "stock": [100, 100], "fresh": [60, 10]})
    hist = sectors.append_history(snap, tmp_path / "s.csv", date(2026, 11, 1))
    official = pd.DataFrame({"sector": ["b"], "shortage_score": [2.4],
                             "employment_change_pct": [None]})
    out = sectors.build(snap, hist, cfg, official, date(2026, 11, 1))
    # No verdict from a single snapshot; an official shortage score still counts.
    assert list(out["status"]) == ["pending", "shortage"]
    assert list(out["fresh_share"]) == [0.6, 0.1]


def _facets(stock, fresh):
    def handler(params):
        counts = fresh if "veroeffentlichtseit" in params else stock
        return FakeResponse({"maxErgebnisse": 1, "facetten": {"berufsfeld": {"counts": counts}}})
    return handler


def test_sector_snapshot_sums_fields_from_two_requests():
    cfg = pd.DataFrame({"sector": ["it", "ads"], "label_en": ["IT", "Ads"],
                        "berufsfeld": ["Informatik|Softwareentwicklung", "Werbung"]})
    stock = {"Informatik": 100, "Softwareentwicklung": 50, "Werbung": 30, "Other": 9}
    fresh = {"Informatik": 40, "Softwareentwicklung": 10, "Werbung": 3}
    session, http = polite({"arbeitsagentur": _facets(stock, fresh)})
    snap = sectors.snapshot(session, cfg, fresh_days=28)
    assert list(snap["stock"]) == [150, 30] and list(snap["fresh"]) == [50, 3]
    assert len(http.calls) == 2 and http.calls[1][1]["veroeffentlichtseit"] == 28


def test_sector_snapshot_rejects_unknown_field_names():
    cfg = pd.DataFrame({"sector": ["x"], "label_en": ["X"], "berufsfeld": ["Typo"]})
    session, _ = polite({"arbeitsagentur": _facets({"Informatik": 1}, {"Informatik": 1})})
    with pytest.raises(ValueError, match="Typo"):
        sectors.snapshot(session, cfg, fresh_days=28)


def test_configured_sector_fields_are_unique():
    fields = [f for cell in load_sectors()["berufsfeld"] for f in cell.split("|")]
    assert len(fields) == len(set(fields)) and load_sectors()["sector"].is_unique


# --- manual inputs and end-to-end build ----------------------------------------------------

def test_manual_loader_validates(tmp_path):
    assert manual.load("rents.csv", tmp_path) is None
    (tmp_path / "rents.csv").write_text("city,wg_room_eur\nDortmund,400\n")
    with pytest.raises(ValueError, match="missing columns"):
        manual.load("rents.csv", tmp_path)
    (tmp_path / "rents.csv").write_text(
        "city,wg_room_eur,rent_eur_m2,period,source\nDortmund,400,,2026,x\nDortmund,410,,2026,x\n")
    with pytest.raises(ValueError, match="duplicate"):
        manual.load("rents.csv", tmp_path)


def test_build_end_to_end(tmp_path):
    manual_dir, out_dir = tmp_path / "manual", tmp_path / "out"
    manual_dir.mkdir()
    (manual_dir / "rents.csv").write_text(
        "city,wg_room_eur,rent_eur_m2,period,source\nDortmund,420,,WS 2026/27,Test source\n"
        "Berlin,650,,WS 2026/27,Test source\n", encoding="utf-8")
    (manual_dir / "students.csv").write_text(
        "city,students_total,students_international,semester,source\n"
        "Dortmund,50000,6000,WS 2025/26,Test\nBerlin,200000,45000,WS 2025/26,Test\n",
        encoding="utf-8")
    payload = fixture("ba_search.json")
    payload["facetten"]["berufsfeld"]["counts"] = {
        f: 10 for cell in load_sectors()["berufsfeld"] for f in cell.split("|")}
    session, _ = polite({
        "arbeitsagentur": FakeResponse(payload),
        "arbeitnow": FakeResponse(fixture("arbeitnow.json")),
    })
    meta = build(load_settings(), session=session, manual_dir=manual_dir, out_dir=out_dir,
                 history_dir=tmp_path / "hist", today=date(2026, 11, 14), log=lambda m: None)
    assert meta["sample"] is False
    assert {k: v["status"] for k, v in meta["layers"].items()} == {
        "rents": "manual", "students": "manual", "jobs": "live", "jobs_other": "live",
        "sectors": "live"}
    cities = {c["city"]: c for c in json.loads((out_dir / "cities.json").read_text())}
    assert len(cities) == len(load_cities())
    assert cities["Dortmund"]["rent_monthly"] == 420 and cities["Dortmund"]["jobs_total"] == 3
    assert cities["Berlin"]["other_en"] == 1
    assert cities["Aachen"]["rent_monthly"] is None  # no invented values for missing inputs
    assert len(json.loads((out_dir / "sectors.json").read_text())) == len(load_sectors())
    assert (tmp_path / "hist" / "sectors.csv").exists()


def test_build_records_source_failure_instead_of_crashing(tmp_path):
    session, _ = polite({})  # every request 404s
    meta = build(load_settings(), session=session, manual_dir=tmp_path, out_dir=tmp_path / "o",
                 history_dir=tmp_path / "h", log=lambda m: None)
    assert meta["layers"]["jobs"]["status"] == "error"
    assert meta["layers"]["rents"]["status"] == "missing"


def test_city_config_is_consistent():
    cities = load_cities()
    states = {f["properties"]["id"] for f in json.loads(
        (Path(__file__).parents[1] / "docs/data/states.geojson").read_text())["features"]}
    assert cities["city"].is_unique and set(cities["state_id"]) <= states
    assert cities["lat"].between(47, 55.1).all() and cities["lon"].between(5.8, 15.1).all()

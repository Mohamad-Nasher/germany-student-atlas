"""Classify a job posting as English or German from its text.

A small, transparent word-list scorer rather than a black-box model: job titles
are short, and a reader of this repo should be able to see why a posting was
labelled the way it was. Returns "en", "de" or "unknown".
"""

from __future__ import annotations

import re

_DE = {
    "werkstudent", "werkstudentin", "werkstudenten", "studentische", "studentischer",
    "aushilfe", "hilfskraft", "mitarbeiter", "mitarbeiterin", "praktikant", "praktikum",
    "im", "für", "fuer", "und", "bereich", "der", "die", "das", "mit", "bei", "zur", "zum",
    "als", "unterstützung", "entwicklung", "vertrieb", "einkauf", "buchhaltung", "personal",
    "kundenservice", "verkauf", "lager", "teilzeit", "vollzeit", "abteilung", "schwerpunkt",
    "wir", "sie", "ihre", "aufgaben", "kenntnisse", "oder", "unser", "eine", "einen",
    "tätigkeit", "studium", "ab", "sofort", "stunden", "woche", "technik", "informatik",
}
_EN = {
    "working", "student", "intern", "internship", "the", "and", "for", "of", "with", "at",
    "our", "team", "you", "your", "we", "are", "to", "in", "development", "engineering",
    "sales", "marketing", "finance", "operations", "support", "research", "business",
    "data", "analyst", "assistant", "software", "customer", "success", "product",
    "management", "people", "talent", "supply", "chain", "part", "time", "skills",
    "experience", "responsibilities", "will", "about", "join", "looking",
}
# Words that appear in both languages' job titles and so carry no signal.
_NEUTRAL = {"m", "w", "d", "f", "x", "it", "hr", "in", "manager", "controlling", "online"}
_TOKEN = re.compile(r"[a-zäöüß]+", re.IGNORECASE)


def classify(text: str | None) -> str:
    if not text:
        return "unknown"
    lowered = text.lower()
    tokens = [t for t in _TOKEN.findall(lowered) if t not in _NEUTRAL]
    de = sum(t in _DE for t in tokens)
    en = sum(t in _EN for t in tokens)
    # Umlauts and ß are strong evidence of German.
    de += 2 * len(re.findall(r"[äöüß]", lowered))
    # "in" is neutral alone, but "(m/w/d)" style tags say nothing either way.
    if de == en:
        return "unknown"
    return "de" if de > en else "en"

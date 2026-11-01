"""Transparent rules: all domain language lives here, not in the CSV adapter."""
from __future__ import annotations
import re
from datetime import date
from difflib import SequenceMatcher

# A deliberately tiny schema ontology. Expand via user-supplied vocabularies later.
FIELD_ALIASES: dict[str, dict[str, float]] = {
    "register_id": {"reg id": 1, "registry id": 1, "site ref": .98, "site reference": .98,
                    "site id": .97, "reference": .70, "ref": .60, "id": .55},
    "address": {"site address": 1, "street address": 1, "address": 1, "addr": .95,
                "location": .76, "street": .80},
    "local_authority": {"local authority": 1, "council": .96, "la code": .89,
                        "authority": .94, "municipality": .90},
    "status": {"current status": 1, "site status": 1, "status": 1, "state": .70},
    "recorded_date": {"date added": .98, "entry date": .97, "recorded date": 1,
                      "added on": .96, "date": .55},
    "latitude": {"latitude": 1, "lat": .97},
    "longitude": {"longitude": 1, "lon": .97, "lng": .97},
}


def clean_header(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def header_similarity(source_field: str, target: str) -> float:
    key = clean_header(source_field)
    aliases = FIELD_ALIASES[target]
    if key in aliases:
        return aliases[key]
    # Fuzzy similarity is deliberately limited: generic fields like 'name'
    # must not get a high semantic score merely by string similarity.
    ratio = max((SequenceMatcher(None, key, alias).ratio() for alias in aliases), default=0)
    return round(ratio * .58, 3)


def normalize_value(value: str, field: str) -> str:
    v = re.sub(r"\s+", " ", value.casefold().strip())
    v = re.sub(r"[.,;]", "", v)
    if field == "address":
        v = re.sub(r"\b(st|str)\b", "street", v)
        v = re.sub(r"\b(rd)\b", "road", v)
    if field in {"register_id", "status", "local_authority"}:
        v = re.sub(r"[^\w]+", "", v)
    return v


def value_compatible(value: str, field: str) -> bool:
    value = value.strip()
    if not value:
        return True
    if field == "address":
        # Address is inherently heterogeneous; test for plausible street/lot format.
        return bool(re.search(r"\d", value) and re.search(r"[A-Za-z]", value))
    if field == "register_id":
        return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _./-]{0,39}", value))
    if field == "status":
        return bool(re.fullmatch(r"[A-Za-z][A-Za-z _/-]{1,49}", value))
    if field == "local_authority":
        return bool(re.search(r"[A-Za-z]", value) and len(value) <= 100)
    if field == "recorded_date":
        try:
            date.fromisoformat(value)
            return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
        except ValueError:
            return False
    if field in {"latitude", "longitude"}:
        try:
            n = float(value)
            return -90 <= n <= 90 if field == "latitude" else -180 <= n <= 180
        except ValueError:
            return False
    raise KeyError(field)


def pattern(values: list[str]) -> str:
    if not values:
        return "empty"
    if all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in values):
        return "iso_date"
    if all(re.fullmatch(r"-?\d+(?:\.\d+)?", v) for v in values):
        return "numeric"
    if all(bool(re.search(r"\d", v) and re.search(r"[A-Za-z]", v)) for v in values):
        return "alphanumeric"
    return "text"

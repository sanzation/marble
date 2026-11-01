"""Small, explicit school schema vocabulary; no learned ontology or ID namespace.

Address components are used only as match evidence. Composite schema mappings
stay review and never split or rewrite source cells in the preview.
"""
from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
import hashlib
from itertools import combinations
import re

from .models import Check, Evidence, Hypothesis, SourceBatch, SourceRecord

HEADERS = {
    "Schulnummer": "school_id", "Schulnr": "school_id", "BSN": "school_id",
    "Amtliche Schulbezeichnung": "school_name", "Schulname": "school_name", "Name der Schule": "school_name",
    "Schulbezeichnung_1": "school_name", "Schulbezeichnung_2": "school_name", "Schulbezeichnung_3": "school_name",
    "Kurzbezeichnung": "school_name",
    "Schulform": "school_type", "Schulart": "school_type",
    "Rechtsform": "operator", "Traeger": "operator", "Träger": "operator",
    "PLZ": "postal_code", "Ort": "city", "Ortsteil": "city_district", "Bezirk": "district",
    "Strasse": "street_address", "Straße": "street_address", "Hausnummer": "street_address", "Adresse": "street_address",
    "Rechtswert": "easting", "Hochwert": "northing", "x_25833": "easting", "y_25833": "northing",
    "UTMRechtswert": "easting", "UTMHochwert": "northing", "EPSG": "crs",
    "Stand": "as_of_date", "Schulbetriebsdatum": "as_of_date",
}
REVIEW_ROLES = {"street_address", "easting", "northing", "operator"}


def _id(*parts: str) -> str:
    return "hyp-" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def column_roles(batch: SourceBatch) -> dict[str, str]:
    # Require a school identifier/name header, not just a coincidental PLZ.
    if not any(HEADERS.get(c) in {"school_id", "school_name"} for c in batch.columns):
        return {}
    return {c: HEADERS[c] for c in batch.columns if c in HEADERS}


def discover_school_fields(batches: list[SourceBatch]) -> list[Hypothesis]:
    result = []
    for batch in batches:
        for column, role in column_roles(batch).items():
            review = role in REVIEW_ROLES or column.startswith("Schulbezeichnung_") or column == "Kurzbezeichnung"
            result.append(Hypothesis(
                hypothesis_id=_id("school-field", batch.source_id, column, role), kind="field_mapping",
                source_id=batch.source_id, source_field=column, target=role, score=.7 if review else .95,
                disposition="review" if review else "accepted",
                evidence=[Evidence(signal="explicit_school_header", strength=.95,
                                   detail=f"Known school vocabulary: {column} -> {role}; not generic schema learning")],
                checks=[Check(name="safe_one_to_one", passed=not review,
                              result="Composite address, name parts, operator semantics or CRS require review" if review
                              else "Direct field role; values are retained verbatim")]))
    return result


def _text(value: str) -> str:
    return re.sub(r"[^\w]+", "", value.casefold())


def _street(value: str) -> str:
    # A comparator only, never a source-value transform or accepted alias.
    return _text(value.casefold().replace("str.", "straße").replace("strasse", "straße"))


def record_view(batch: SourceBatch, record: SourceRecord) -> dict[str, str]:
    roles = column_roles(batch)
    view = {role: record.values.get(column) or "" for column, role in roles.items()}
    street = record.values.get("Strasse") or record.values.get("Straße") or ""
    house = record.values.get("Hausnummer") or ""
    composite = record.values.get("Adresse") or ""
    if composite:
        street = composite.split(",", 1)[0]
        postcode = re.search(r",\s*(\d{5})\b", composite)
        if postcode:
            view["postal_code"] = postcode.group(1)
    view["street_address"] = street + house
    return view


def discover_school_matches(batches: list[SourceBatch]) -> list[Hypothesis]:
    rows = [(batch, record, record_view(batch, record)) for batch in batches if column_roles(batch)
            for record in batch.records]
    # Exact ID/name/street blocking keeps the real NRW file out of an O(n^2)
    # all-pairs loop. Fuzzy name scoring only assesses candidates from a block.
    blocks: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, (_, _, view) in enumerate(rows):
        for role in ("school_id", "school_name", "street_address"):
            value = _street(view.get(role, "")) if role == "street_address" else _text(view.get(role, ""))
            if value:
                blocks[(role, value)].append(index)
    pairs = sorted({pair for indices in blocks.values() for pair in combinations(indices, 2)})
    result = []
    for left_index, right_index in pairs:
        left_batch, a, left = rows[left_index]
        right_batch, b, right = rows[right_index]
        left_id, right_id = left.get("school_id", ""), right.get("school_id", "")
        same_id = bool(left_id and right_id and left_id == right_id)
        conflict = bool(left_id and right_id and left_id != right_id)
        lp, rp = left.get("postal_code", ""), right.get("postal_code", "")
        lc, rc = left.get("city", ""), right.get("city", "")
        location_conflict = bool((lp and rp and lp != rp) or (lc and rc and _text(lc) != _text(rc)))
        street_equal = bool(left["street_address"] and _street(left["street_address"]) == _street(right["street_address"]))
        name_score = SequenceMatcher(None, _text(left.get("school_name", "")), _text(right.get("school_name", ""))).ratio()
        disposition = "rejected" if location_conflict else "review" if conflict or not same_id or not street_equal or name_score < .6 else "accepted"
        score = round(.55 * same_id + .3 * street_equal + .15 * name_score, 3)
        result.append(Hypothesis(
            hypothesis_id=_id("school-pair", left_batch.source_id, a.record_key, right_batch.source_id, b.record_key),
            kind="record_match", source_id=f"{left_batch.source_id}|{right_batch.source_id}",
            left_record=f"{left_batch.source_id}:{a.record_key}", right_record=f"{right_batch.source_id}:{b.record_key}",
            target="same_real_world_entity", score=score, disposition=disposition,
            checks=[Check(name="no_id_conflict", passed=not conflict, result=f"IDs: {left_id or 'missing'} / {right_id or 'missing'}; namespaces are not assumed equivalent"),
                    Check(name="location_compatible", passed=not location_conflict, result=f"Postal codes: {lp or 'missing'} / {rp or 'missing'}"),
                    Check(name="street_comparator_equal", passed=street_equal, result="Field-scoped textual comparator; source addresses unchanged"),
                    Check(name="identifier_agreement", passed=same_id, result="Absent or conflicting ID cannot produce an accepted school match")],
            evidence=[Evidence(signal="school_name_similarity", strength=name_score,
                               detail=f"{left.get('school_name', '')} / {right.get('school_name', '')}; match evidence is never normalization authority")]))
    return result

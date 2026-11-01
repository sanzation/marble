"""Reproduce the labelled school evaluation and the independent real-NRW profile.

The production engine never reads truth.json. This evaluator only compares its
outputs with those pre-existing labels; it does not tune the engine or labels.
Run from the project root: python scripts/benchmark_schulen.py
"""
from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import io
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys

from marble import inspect_csvs
from marble.ingest import load_csv

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "schulen_de"
OUTPUT = ROOT / "docs" / "validation" / "schulen_de"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    truth = json.loads((BASE / "truth.json").read_text(encoding="utf-8"))
    sources = {key: load_csv(BASE / spec["file"]) for key, spec in truth["sources"].items()}
    paths = [BASE / spec["file"] for spec in truth["sources"].values()]
    paths.append(BASE / truth["nondomain_check"]["file"])
    report = inspect_csvs(paths, alias_packs=[BASE / "alias_packs" / "schulen-de.json"],
                          output_dir=ROOT / "out" / "schulen_de", duckdb_path=ROOT / "out" / "schulen_de.duckdb")
    rows = []
    for case in truth["expected_normalization"]:
        source_id = sources[case["src"]].source_id
        matches = [p for p in report.normalization_proposals
                   if p.source_id == source_id and p.canonical_field == case["field"]
                   and p.operation == case["op"] and p.raw_value == case["raw"]
                   and (case["row"] == "all" or p.row_number == case["row"] + 1)]
        actual = sorted({p.disposition for p in matches})
        correct = bool(matches) and actual == [case["disposition"]] and all(
            p.proposed_value == case["proposed"] and p.candidates == case.get("candidates", []) for p in matches)
        rows.append({"id": case["id"], "operation": case["op"], "tier": case.get("tier", "core"),
                     "expected": case["disposition"], "before": "not_generated",
                     "before_reason": "v0.0.1 has no proposals/alias_packs API; original corpus also fails cp1252 decoding",
                     "actual": actual or ["missing"], "matches_truth": correct,
                     "expected_value": case["proposed"], "actual_values": sorted({p.proposed_value for p in matches}, key=lambda v: v or ""),
                     "expected_candidates": case.get("candidates", []),
                     "proposal_ids": [p.proposal_id for p in matches]})

    def ref(member):
        source, index = member
        batch = sources[source]
        return f"{batch.source_id}:{batch.records[index - 1].record_key}"

    matches = [h for h in report.hypotheses if h.kind == "record_match"]
    accepted = {frozenset((h.left_record, h.right_record)) for h in matches if h.disposition == "accepted"}
    labelled_pairs = {frozenset((ref(a), ref(b))) for entity in truth["entities"]
                      for a, b in combinations(entity["members"], 2)}
    candidate_pairs = {frozenset((h.left_record, h.right_record)) for h in matches}
    entities = []
    for entity in truth["entities"]:
        for a, b in combinations(entity["members"], 2):
            pair = frozenset((ref(a), ref(b)))
            entities.append({"entity": entity["id"], "a": a, "b": b,
                             "expected": entity.get("expected_disposition", "same entity; no disposition specified"),
                             "actual": [h.disposition for h in matches if frozenset((h.left_record, h.right_record)) == pair] or ["missing"]})
    negative_pairs = []
    for case in truth["must_not_merge"]:
        pair = frozenset((ref(case["a"]), ref(case["b"])))
        negative_pairs.append({**case, "actual": [h.disposition for h in matches
                                                 if frozenset((h.left_record, h.right_record)) == pair] or ["no_candidate"],
                               "has_accepted_match": pair in accepted})
    raw_preserved = True
    columns_preserved = True
    for path in paths:
        batch = load_csv(path)
        for record in batch.records:
            preview = next(p for p in report.canonical_preview if p.source_id == batch.source_id and p.record_key == record.record_key)
            columns_preserved &= len(preview.canonical_fields) + len(preview.unmapped_fields) == len(record.values)
            raw_preserved &= Counter(preview.canonical_fields.values()) + Counter(preview.unmapped_fields.values()) == Counter(record.values.values())
    repeated = inspect_csvs(paths, alias_packs=[BASE / "alias_packs" / "schulen-de.json"])
    evaluation = {"fixture_only": True, "run_id": report.run_id, "metrics": report.metrics,
                  "normalization": rows, "entities": entities, "must_not_merge": negative_pairs,
                  "labelled_positive_pairs": len(labelled_pairs), "positive_pairs_with_candidate": len(labelled_pairs & candidate_pairs),
                  "accepted_matches": len(accepted), "accepted_matches_outside_labelled_entities": len(accepted - labelled_pairs),
                  "raw_values_changed": 0 if raw_preserved else "FAILED", "lost_columns": 0 if columns_preserved else "FAILED",
                  "deterministic_full_report": report.model_dump() == repeated.model_dump(),
                  "fixture_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                     for path in [*paths, BASE / "truth.json", BASE / "alias_packs" / "schulen-de.json"]}}
    write_json(OUTPUT / "evaluation.json", evaluation)
    with (OUTPUT / "normalization-dispositions.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["N-ID", "operation", "tier", "expected", "before", "actual", "matches_truth"])
        writer.writerows([r["id"], r["operation"], r["tier"], r["expected"], r["before"], ",".join(r["actual"]), r["matches_truth"]] for r in rows)

    real_path = BASE / "real_nrw" / "schuldaten.csv"
    real = load_csv(real_path)
    crs_counts = Counter(r.values.get("EPSG") for r in real.records)
    provenance = {
        "publisher": "Ministerium für Schule und Bildung des Landes Nordrhein-Westfalen",
        "source_url": "https://www.schulministerium.nrw.de/BiPo/OpenData/Schuldaten/schuldaten.csv",
        "resolved_url": "https://apps.schulministerium.nrw.de/BiPo/OpenData/Schuldaten/schuldaten.csv",
        "dataset_url": "https://data.gov.de/suche/daten/schulgrunddaten-nrw?ids=651a0ec7-0e61-4219-b4a7-ffcfbb7b15b0",
        "license": "dl-de/by-2-0", "license_url": "https://www.govdata.de/dl-de/by-2-0",
        "retrieved_at": datetime.fromtimestamp(real_path.stat().st_mtime, timezone.utc).isoformat(),
        "http_last_modified": "Sun, 01 Nov 2026 05:05:14 GMT",
        "sha256": hashlib.sha256(real_path.read_bytes()).hexdigest(), "bytes": real_path.stat().st_size,
        "modifications": "none; downloaded bytes preserved", "declared_crs": None,
        "crs_column_counts": dict(crs_counts),
        "note": "No dataset-wide CRS asserted: some rows contain the literal null. Catalogue description mentions Gauß-Krüger; actual cells declare EPSG:25832."
    }
    write_json(real_path.parent / "provenance.json", provenance)
    metadata = {"schuldaten": {key: provenance[key] for key in ("publisher", "license", "license_url", "retrieved_at", "declared_crs")}}
    write_json(real_path.parent / "source_metadata.json", metadata)
    # Exercise the full pipeline as an ingestion/structure check. Synthetic rows
    # have no labelled relationship with real schools; do not score real matches.
    real_report = inspect_csvs([real_path, paths[0]], source_metadata=metadata)
    write_json(OUTPUT / "real-nrw-profiles.json", [p.model_dump(mode="json") for p in real_report.source_profiles])
    text = real_path.read_bytes().decode("utf-8")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=";")
    assert next(reader) == ["sep=", ""]
    header = next(reader)
    assert header[-1] == ""
    header = header[:-1]
    expected_rows = [dict(zip(header, row, strict=True)) for row in reader]
    structure = {"real_rows": len(real.records), "synthetic_nrw_rows": len(sources["nrw"].records),
                 "real_columns": real.columns, "synthetic_columns": sources["nrw"].columns,
                 "ingestion": real.ingestion.model_dump() if real.ingestion else None,
                 "independent_csv_roundtrip_equal": [r.values for r in real.records] == expected_rows,
                 "unique_school_ids": len({r.values["Schulnummer"] for r in real.records}),
                 "school_form_codes": dict(Counter(r.values["Schulform"] for r in real.records)),
                 "legal_form_codes": dict(Counter(r.values["Rechtsform"] for r in real.records)),
                 "school_status_codes": dict(Counter(r.values["Schulbetriebsschluessel"] for r in real.records)),
                 "crs_column_counts": dict(crs_counts),
                 "literal_null_coordinates": sum(r.values["UTMRechtswert"] == "null" or r.values["UTMHochwert"] == "null" for r in real.records),
                 "contains_decimal_comma_coordinates": any("," in (r.values["UTMRechtswert"] or "") for r in real.records),
                 "match_accuracy": "not measured: no real-data entity or normalization labels",
                 "provenance": provenance}
    write_json(OUTPUT / "real-nrw-comparison.json", structure)
    proposal = next(p for p in report.normalization_proposals if p.candidates and p.raw_value == "KGS Sankt Martin")
    explain = subprocess.run([sys.executable, "-X", "utf8", "-m", "marble.cli", "explain",
                              str(ROOT / "out" / "schulen_de" / "report.json"), "--kind", "normalization", "--id", proposal.proposal_id],
                             capture_output=True, encoding="utf-8", check=True)
    (OUTPUT / "explain-example.txt").write_text(explain.stdout, encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "normalization_cases_matched": sum(r["matches_truth"] for r in rows),
                      "metrics": report.metrics, "real_rows": len(real.records), "raw_roundtrip": structure["independent_csv_roundtrip_equal"]}, indent=2))


if __name__ == "__main__":
    main()

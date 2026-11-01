"""Acceptance criteria labelled in schulen_de/truth.json before implementation.

accepted always means heuristically accepted, never human confirmed.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from marble import inspect_csvs
from marble.ingest import load_csv
from marble.models import InspectionReport

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "schulen_de"
TRUTH = json.loads((BASE / "truth.json").read_text(encoding="utf-8"))
PACK = BASE / "alias_packs" / "schulen-de.json"
FILES = [BASE / source["file"] for source in TRUTH["sources"].values()]
FILES.append(BASE / TRUTH["nondomain_check"]["file"])


@pytest.fixture(scope="module")
def school_report():
    return inspect_csvs(FILES, alias_packs=[PACK])


def normalization_matches(report, case):
    source_id = Path(TRUTH["sources"][case["src"]]["file"]).stem
    return [p for p in report.normalization_proposals
            if p.source_id == source_id and p.canonical_field == case["field"]
            and p.operation == case["op"] and p.raw_value == case["raw"]
            and (case["row"] == "all" or p.row_number == case["row"] + 1)]


@pytest.mark.parametrize("case", TRUTH["expected_normalization"], ids=lambda case: case["id"])
def test_expected_normalization_disposition(school_report, case):
    proposals = normalization_matches(school_report, case)
    assert proposals, f"{case['id']}: expected {case['disposition']}; actual=missing"
    for proposal in proposals:
        assert proposal.disposition == case["disposition"], (
            f"{case['id']}: expected={case['disposition']}; actual={proposal.disposition}")
        assert proposal.proposed_value == case["proposed"]
        assert proposal.candidates == case.get("candidates", [])
        assert proposal.evidence and proposal.checks
        assert proposal.recipe_candidate
    if case["id"] == "N11":
        assert len(proposals) == 8, "date proposal must cover every Düsseldorf row"


@pytest.mark.parametrize("source", list(TRUTH["sources"].values()), ids=lambda source: source["file"])
def test_source_encoding_delimiter_and_raw_roundtrip(source):
    path = BASE / source["file"]
    with path.open(encoding=source["encoding"], newline="") as fh:
        expected = list(csv.DictReader(fh, delimiter=source["delimiter"]))
    batch = load_csv(path)
    assert [record.values for record in batch.records] == expected
    assert batch.ingestion is not None
    assert batch.ingestion.encoding == source["encoding"]
    assert batch.ingestion.delimiter == source["delimiter"]


def _ref(member):
    source, row = member
    batch = load_csv(BASE / TRUTH["sources"][source]["file"])
    return f"{batch.source_id}:{batch.records[row - 1].record_key}"


@pytest.mark.parametrize("case", TRUTH["must_not_merge"], ids=lambda case: str(case["a"]) + str(case["b"]))
def test_must_not_merge(school_report, case):
    pair = {_ref(case["a"]), _ref(case["b"])}
    matches = [h for h in school_report.hypotheses if h.kind == "record_match"
               and {h.left_record, h.right_record} == pair]
    assert not any(h.disposition == "accepted" for h in matches), case["reason"]


def test_conflicting_school_id_is_review(school_report):
    entity = next(e for e in TRUTH["entities"] if e["id"] == "E04")
    pair = {_ref(member) for member in entity["members"]}
    matches = [h for h in school_report.hypotheses if h.kind == "record_match"
               and {h.left_record, h.right_record} == pair]
    assert len(matches) == 1
    assert matches[0].disposition == entity["expected_disposition"]
    assert any(c.name == "no_id_conflict" and not c.passed for c in matches[0].checks)


def test_schema_uncertainties_remain_review(school_report):
    mappings = [h for h in school_report.hypotheses if h.kind == "field_mapping"]
    for role in ("school_id", "school_name", "school_type"):
        for source in TRUTH["sources"]:
            field = TRUTH["schema_mapping"][role][source]
            source_id = Path(TRUTH["sources"][source]["file"]).stem
            assert any(h.source_id == source_id and h.source_field == field
                       and h.target == role and h.disposition != "rejected" for h in mappings)
    assert not any(h.source_field == "Nr." and h.target == "school_id" for h in mappings)
    for field in ("Adresse", "Strasse", "Hausnummer", "Rechtswert", "Hochwert", "x_25833", "y_25833", "Rechtsform"):
        relevant = [h for h in mappings if h.source_field == field]
        assert relevant, field
        assert all(h.disposition == "review" for h in relevant), field


def test_opt_in_and_nondomain_scope(school_report):
    without_pack = inspect_csvs(FILES)
    assert not any(p.operation in {"alias_lookup", "category_equivalence"}
                   for p in without_pack.normalization_proposals)
    assert not any(p.source_id == "nondomain_kgs" and p.operation == "alias_lookup"
                   for p in school_report.normalization_proposals)
    # Context comes from the same raw row, not a guessed entity match.
    n09 = next(c for c in TRUTH["expected_normalization"] if c["id"] == "N09")
    assert all(p.disposition == "review" for p in normalization_matches(school_report, n09))


def test_global_invariants_and_old_report_compatibility(school_report, tmp_path):
    assert school_report.metrics["actual_entities_merged"] == TRUTH["global_invariants"]["entity_merges"]
    for path in FILES:
        batch = load_csv(path)
        for record in batch.records:
            preview = next(p for p in school_report.canonical_preview
                           if p.source_id == batch.source_id and p.record_key == record.record_key)
            assert len(preview.canonical_fields) + len(preview.unmapped_fields) == len(record.values)
            assert sorted(preview.canonical_fields.values(), key=lambda v: v or "") == sorted(
                [v for k, v in record.values.items() if k not in preview.unmapped_fields], key=lambda v: v or "")
            assert all(record.values[k] == v for k, v in preview.unmapped_fields.items())
    again = inspect_csvs(FILES, alias_packs=[PACK], output_dir=tmp_path)
    assert again.model_dump() == school_report.model_dump()
    assert len({p.proposal_id for p in again.normalization_proposals}) == len(again.normalization_proposals)
    assert (tmp_path / "normalization_proposals.json").is_file()
    assert InspectionReport.model_validate_json((tmp_path / "report.json").read_text(encoding="utf-8")) == again
    old = ROOT / "examples" / "three_csv" / "sample_output" / "report.json"
    assert InspectionReport.model_validate_json(old.read_text(encoding="utf-8")).normalization_proposals == []


def test_csv_preamble_and_unnamed_trailing_header(tmp_path):
    path = tmp_path / "official_style.csv"
    # Actual NRW format: sep preamble and one extra trailing header delimiter.
    path.write_bytes('sep=;\nSchulnummer;Schulbezeichnung_1;\n"001234";"Schule Köln"\n'.encode("cp1252"))
    batch = load_csv(path)
    assert batch.columns == ["Schulnummer", "Schulbezeichnung_1"]
    assert batch.records[0].values == {"Schulnummer": "001234", "Schulbezeichnung_1": "Schule Köln"}
    assert batch.records[0].row_number == 3
    assert batch.ingestion is not None
    assert batch.ingestion.preamble_lines == 1
    assert batch.ingestion.ignored_empty_header_columns == 1


def test_cli_normalization_explain(school_report, tmp_path):
    inspect_csvs(FILES, alias_packs=[PACK], output_dir=tmp_path)
    proposal = next(p for p in school_report.normalization_proposals if p.operation == "alias_lookup")
    result = subprocess.run([sys.executable, "-m", "marble.cli", "explain", str(tmp_path / "report.json"),
                             "--kind", "normalization", "--id", proposal.proposal_id],
                            capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert result.returncode == 0, result.stderr
    assert proposal.proposal_id in result.stdout
    assert proposal.raw_value in result.stdout
    assert "EVIDENCE" in result.stdout and "PASS" in result.stdout


def test_provenance_passthrough(tmp_path):
    provenance = {"publisher": "Synthetic fixture", "license": "test-only", "license_url": "https://example.test/license",
                  "retrieved_at": "2026-11-01T12:00:00Z", "declared_crs": "EPSG:25832"}
    report = inspect_csvs(FILES, source_metadata={FILES[0].stem: provenance})
    profile = next(p for p in report.source_profiles if p.source_id == FILES[0].stem)
    assert all(getattr(profile, key) == value for key, value in provenance.items())


def test_ambiguous_pack_context_does_not_use_substring_or_guessed_type(tmp_path):
    path = tmp_path / "context.csv"
    path.write_text('Schulname;Schulart\nKGS Test;GS\nKGS Sonst;Nicht-Gesamtschule\nXKGS Test;Gesamtschule\n', encoding="utf-8")
    report = inspect_csvs([path, FILES[0]], alias_packs=[PACK])
    proposals = [p for p in report.normalization_proposals if p.source_id == path.stem and p.operation == "alias_lookup"]
    assert not any(p.disposition == "accepted" and p.canonical_field == "school_name" for p in proposals)
    assert not any(p.raw_value.startswith("XKGS") for p in proposals)


def test_format_validation_keeps_ambiguous_and_invalid_dates(tmp_path):
    path = tmp_path / "dates.csv"
    path.write_text('Schulname;Stand\nTest A;01.02.2023\nTest B;31.02.2023\n', encoding="utf-8")
    report = inspect_csvs([path, FILES[0]])
    dates = [p for p in report.normalization_proposals if p.source_id == path.stem and p.operation == "parse_date_de"]
    assert [(p.disposition, p.proposed_value) for p in dates] == [("review", "2023-02-01"), ("rejected", None)]


def test_competing_packs_remain_review_and_config_changes_run_id(tmp_path):
    conflicting = json.loads(PACK.read_text(encoding="utf-8"))
    conflicting["pack_id"] = "competing-schools"
    conflicting["entries"][0]["canonical"] = "Andere Schule"
    path = tmp_path / "conflicting.json"
    path.write_text(json.dumps(conflicting), encoding="utf-8")
    first = inspect_csvs(FILES, alias_packs=[PACK])
    second = inspect_csvs(FILES, alias_packs=[PACK, path])
    assert first.run_id != second.run_id
    choices = [p for p in second.normalization_proposals if p.operation == "alias_lookup" and p.raw_value == "Goethe-Gym."]
    assert len(choices) == 2 and all(p.disposition == "review" for p in choices)

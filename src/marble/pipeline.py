"""Inspect first; do not coerce, merge or overwrite entities."""
from __future__ import annotations
from collections.abc import Mapping, Sequence
import csv
import hashlib
import json
from pathlib import Path
from .discovery import (
    build_recipe_draft, discover_entity_grains, discover_field_hypotheses,
    discover_record_matches, make_preview,
)
from .ingest import load_csv
from .models import InspectionReport, SourceBatch, SourceMetadata
from .normalization import discover_normalizations, load_alias_packs
from .profile import profile_batch


def inspect_csvs(paths: Sequence[str | Path], *, output_dir: str | Path | None = None,
                 duckdb_path: str | Path | None = None,
                 alias_packs: Sequence[str | Path] = (),
                 source_metadata: Mapping[str, Mapping[str, str | None]] | None = None) -> InspectionReport:
    """Run a deterministic, inspectable CSV-only discovery pass for >=2 CSVs."""
    if not 2 <= len(paths) <= 20:
        raise ValueError("Provide between 2 and 20 CSV inputs")
    batches: list[SourceBatch] = [load_csv(p) for p in paths]
    if len(set(b.source_id for b in batches)) != len(batches):
        raise ValueError("CSV filenames must have unique stems (source IDs)")
    metadata = {key: SourceMetadata.model_validate(value) for key, value in (source_metadata or {}).items()}
    if set(metadata) - {batch.source_id for batch in batches}:
        raise ValueError("Source metadata keys must be CSV source IDs (filename stems)")
    batches = [SourceBatch.model_validate({**batch.model_dump(), **metadata[batch.source_id].model_dump()})
               if batch.source_id in metadata else batch for batch in batches]
    packs = load_alias_packs(alias_packs)
    profiles = [profile_batch(b) for b in batches]
    mappings = discover_field_hypotheses(batches)
    grains = discover_entity_grains(batches, mappings)
    record_matches = discover_record_matches(batches, mappings)
    hypotheses = [*mappings, *grains, *record_matches]
    draft = build_recipe_draft(batches, hypotheses)
    normalizations = discover_normalizations(batches, packs)
    draft.normalization_proposal_ids = [p.proposal_id for p in normalizations]
    draft.generated_by = "marble-discovery-0.0.2"
    if normalizations:
        draft.recipe_id = "draft-" + hashlib.sha256(json.dumps(
            [draft.recipe_id, draft.normalization_proposal_ids]).encode()).hexdigest()[:16]
    preview = make_preview(batches, draft)
    run_data = sorted((b.source_id, sorted(r.content_hash for r in b.records)) for b in batches)
    config = {"engine": "0.0.2", "sources": run_data, "packs": [p.model_dump() for p in packs],
              "metadata": {key: value.model_dump() for key, value in sorted(metadata.items())}}
    run_id = "run-" + hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    metrics = {
        "sources": len(batches), "source_records": sum(len(b.records) for b in batches),
        "hypotheses": len(hypotheses),
        "field_mappings_accepted": sum(h.kind == "field_mapping" and h.disposition == "accepted" for h in hypotheses),
        "field_mappings_review": sum(h.kind == "field_mapping" and h.disposition == "review" for h in hypotheses),
        "record_matches_accepted_as_hypotheses": sum(h.kind == "record_match" and h.disposition == "accepted" for h in hypotheses),
        "record_matches_rejected": sum(h.kind == "record_match" and h.disposition == "rejected" for h in hypotheses),
        "actual_entities_merged": 0,
        "normalization_proposals": len(normalizations),
        "normalizations_heuristically_accepted": sum(p.disposition == "accepted" for p in normalizations),
        "normalizations_review": sum(p.disposition == "review" for p in normalizations),
        "normalizations_rejected": sum(p.disposition == "rejected" for p in normalizations),
        "normalizations_applied": 0,
    }
    report = InspectionReport(run_id=run_id, source_profiles=profiles, hypotheses=hypotheses,
                              recipe_draft=draft, canonical_preview=preview, metrics=metrics,
                              normalization_proposals=normalizations)
    if output_dir is not None:
        export_report(report, output_dir)
    if duckdb_path is not None:
        from .storage import DuckDBInspectionStore
        DuckDBInspectionStore(duckdb_path).write(report, batches)
    return report


def export_report(report: InspectionReport, output_dir: str | Path) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "report.json": report.model_dump(mode="json"),
        "source_profiles.json": [x.model_dump(mode="json") for x in report.source_profiles],
        "hypotheses.json": [x.model_dump(mode="json") for x in report.hypotheses],
        "recipe_draft.json": report.recipe_draft.model_dump(mode="json"),
        "canonical_preview.json": [x.model_dump(mode="json") for x in report.canonical_preview],
        "normalization_proposals.json": [x.model_dump(mode="json") for x in report.normalization_proposals],
    }
    for filename, payload in artifacts.items():
        (output / filename).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (output / "normalization_proposals.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["proposal_id", "source_id", "row_number", "source_field", "canonical_field", "operation",
                         "raw_value", "proposed_value", "candidates", "disposition", "checks"])
        for p in report.normalization_proposals:
            writer.writerow([p.proposal_id, p.source_id, p.row_number, p.source_field, p.canonical_field, p.operation,
                             p.raw_value, p.proposed_value, json.dumps(p.candidates, ensure_ascii=False), p.disposition,
                             "; ".join(f"{c.name}:{'PASS' if c.passed else 'FAIL'}" for c in p.checks)])
    with (output / "hypotheses.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["hypothesis_id", "kind", "source_id", "source_field", "left_record", "right_record", "target", "score", "disposition", "checks", "evidence"])
        for h in report.hypotheses:
            writer.writerow([h.hypothesis_id, h.kind, h.source_id, h.source_field or "", h.left_record or "", h.right_record or "", h.target,
                             h.score, h.disposition, "; ".join(f"{c.name}:{'PASS' if c.passed else 'FAIL'}" for c in h.checks),
                             "; ".join(f"{e.signal}={e.strength:.2f}" for e in h.evidence)])

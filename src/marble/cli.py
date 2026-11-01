from __future__ import annotations
import argparse
import json
from .pipeline import inspect_csvs


def main() -> None:
    parser = argparse.ArgumentParser(prog="marble", description="CSV schema and entity hypotheses, with transparent validation")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Read CSVs, profile, propose, validate and emit report")
    inspect.add_argument("inputs", nargs="+", help="two or more CSV files (three recommended)")
    inspect.add_argument("--out", default="out", help="JSON and CSV reports")
    inspect.add_argument("--db", default="marble.duckdb", help="DuckDB snapshot path")
    inspect.add_argument("--no-db", action="store_true", help="Skip DuckDB write (useful for a dependency-light audit)")
    inspect.add_argument("--alias-pack", action="append", default=[], help="Explicitly activate a field-scoped alias-pack JSON (repeatable)")
    inspect.add_argument("--source-metadata", help="JSON object keyed by source ID with provenance fields")
    explain = sub.add_parser("explain", help="Print evidence and checks for one or more hypotheses")
    explain.add_argument("report", help="path to report.json")
    explain.add_argument("--source", default=None, help="filter by source ID")
    explain.add_argument("--field", default=None, help="filter by raw column name")
    explain.add_argument("--kind", choices=["field_mapping", "entity_grain", "record_match", "normalization"], default=None)
    explain.add_argument("--id", default=None, help="filter by exact hypothesis ID")
    args = parser.parse_args()
    if args.command == "inspect":
        from pathlib import Path
        metadata = json.loads(Path(args.source_metadata).read_text(encoding="utf-8")) if args.source_metadata else None
        report = inspect_csvs(args.inputs, output_dir=args.out,
                              duckdb_path=None if args.no_db else args.db,
                              alias_packs=args.alias_pack, source_metadata=metadata)
        print(json.dumps({"run_id": report.run_id, **report.metrics,
                          "files": args.out, "duckdb": None if args.no_db else args.db}, indent=2))
    elif args.command == "explain":
        from pathlib import Path
        from .models import InspectionReport
        report = InspectionReport.model_validate_json(Path(args.report).read_text(encoding="utf-8"))
        matches = [h for h in report.hypotheses
                   if (args.source is None or h.source_id == args.source)
                   and (args.field is None or h.source_field == args.field)
                   and (args.kind is None or h.kind == args.kind)
                   and (args.id is None or h.hypothesis_id == args.id)]
        normalizations = [p for p in report.normalization_proposals
                          if (args.kind is None or args.kind == "normalization")
                          and (args.source is None or p.source_id == args.source)
                          and (args.field is None or p.source_field == args.field)
                          and (args.id is None or p.proposal_id == args.id)]
        if not matches and not normalizations:
            parser.error("No hypotheses match these filters")
        for h in matches:
            print(f"\n{h.hypothesis_id}  {h.kind}: {h.source_field or h.left_record or ''} -> {h.target}")
            print(f"  source={h.source_id} status={h.disposition} score={h.score:.3f} model={h.model}")
            for e in h.evidence:
                print(f"  EVIDENCE {e.signal}={e.strength:.3f}: {e.detail}")
            for c in h.checks:
                print(f"  {'PASS' if c.passed else 'FAIL'} {c.name}: {c.result}" +
                      (f" ({c.observed:.3f})" if c.observed is not None else ""))
        for p in normalizations:
            print(f"\n{p.proposal_id}  normalization: {p.operation} ({p.canonical_field})")
            print(f"  source={p.source_id} row={p.row_number} field={p.source_field}")
            print(f"  raw={p.raw_value!r} proposed={p.proposed_value!r} candidates={p.candidates}")
            print(f"  status={p.disposition} score={p.score:.3f}; accepted=heuristically accepted, not human confirmed")
            for e in p.evidence:
                print(f"  EVIDENCE {e.signal}={e.strength:.3f}: {e.detail}")
            for c in p.checks:
                print(f"  {'PASS' if c.passed else 'FAIL'} {c.name}: {c.result}")

if __name__ == "__main__":
    main()

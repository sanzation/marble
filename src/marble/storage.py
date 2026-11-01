"""DuckDB adapter. Nothing in discovery imports or depends on this implementation."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Protocol
from .models import InspectionReport, SourceBatch


class InspectionStore(Protocol):
    def write(self, report: InspectionReport, batches: list[SourceBatch]) -> None:
        ...


class DuckDBInspectionStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    def write(self, report: InspectionReport, batches: list[SourceBatch]) -> None:
        try:
            import duckdb
        except ImportError as exc:
            raise RuntimeError("DuckDB is not installed. Install with: pip install -e .") from exc
        con = duckdb.connect(self.path)
        try:
            con.execute("BEGIN TRANSACTION")
            con.execute("CREATE TABLE IF NOT EXISTS source_records (source_id VARCHAR, record_key VARCHAR, row_number INTEGER, content_hash VARCHAR, raw_json VARCHAR)")
            con.execute("CREATE TABLE IF NOT EXISTS source_profiles (source_id VARCHAR, profile_json VARCHAR)")
            con.execute("CREATE TABLE IF NOT EXISTS hypotheses (hypothesis_id VARCHAR, kind VARCHAR, source_id VARCHAR, target VARCHAR, score DOUBLE, disposition VARCHAR, evidence_json VARCHAR)")
            con.execute("CREATE TABLE IF NOT EXISTS recipe_drafts (recipe_id VARCHAR, recipe_json VARCHAR)")
            con.execute("CREATE TABLE IF NOT EXISTS run_reports (run_id VARCHAR, report_json VARCHAR)")
            # This early prototype stores one inspection snapshot per database file.
            # Subsequent inspection replaces it transactionally, not an incremental merge.
            for table in ("source_records", "source_profiles", "hypotheses", "recipe_drafts", "run_reports"):
                con.execute(f"DELETE FROM {table}")
            records = [(r.source_id, r.record_key, r.row_number, r.content_hash, json.dumps(r.values, ensure_ascii=False))
                       for batch in batches for r in batch.records]
            if records:
                con.executemany("INSERT INTO source_records VALUES (?, ?, ?, ?, ?)", records)
            con.executemany("INSERT INTO source_profiles VALUES (?, ?)",
                            [(p.source_id, p.model_dump_json()) for p in report.source_profiles])
            con.executemany("INSERT INTO hypotheses VALUES (?, ?, ?, ?, ?, ?, ?)",
                            [(h.hypothesis_id, h.kind, h.source_id, h.target, h.score, h.disposition,
                              h.model_dump_json()) for h in report.hypotheses])
            con.execute("INSERT INTO recipe_drafts VALUES (?, ?)",
                        [report.recipe_draft.recipe_id, report.recipe_draft.model_dump_json()])
            con.execute("INSERT INTO run_reports VALUES (?, ?)",
                        [report.run_id, report.model_dump_json()])
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

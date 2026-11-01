"""Stable, JSON serializable contracts.  Schema version 1 remains independent of DuckDB."""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    license: str | None = None
    license_url: str | None = None
    publisher: str | None = None
    retrieved_at: str | None = None
    declared_crs: str | None = None


class CSVIngestion(BaseModel):
    encoding: str
    delimiter: str
    preamble_lines: int = 0
    ignored_empty_header_columns: int = 0
    evidence: list[str] = Field(default_factory=list)


class SourceRecord(BaseModel):
    source_id: str
    record_key: str
    row_number: int  # physical CSV row, starting at 2 for a header on row 1
    content_hash: str
    values: dict[str, str | None]


class SourceBatch(Contract, SourceMetadata):
    source_id: str
    uri: str
    columns: list[str]
    records: list[SourceRecord]
    ingestion: CSVIngestion | None = None

    def to_arrow(self):
        """Optional Arrow interface for downstream engines; no Arrow dependency in core."""
        try:
            import pyarrow as pa  # pyright: ignore[reportMissingImports] -- optional arrow extra
        except ImportError as exc:
            raise RuntimeError("Install marble-core-prototype[arrow] for Arrow export") from exc
        cols = {
            "_source_id": [r.source_id for r in self.records],
            "_record_key": [r.record_key for r in self.records],
            "_content_hash": [r.content_hash for r in self.records],
            **{c: [r.values.get(c) for r in self.records] for c in self.columns},
        }
        return pa.table(cols)


class ColumnProfile(BaseModel):
    name: str
    nonempty: int
    distinct_nonempty: int
    completeness: float
    uniqueness: float
    sample_values: list[str]
    detected_pattern: str


class SourceProfile(Contract, SourceMetadata):
    source_id: str
    uri: str
    record_count: int
    columns: list[ColumnProfile]
    ingestion: CSVIngestion | None = None


class Evidence(BaseModel):
    signal: str
    detail: str
    strength: float = Field(ge=0, le=1)


class Check(BaseModel):
    name: str
    passed: bool
    result: str
    observed: float | None = None


class Hypothesis(Contract):
    hypothesis_id: str
    kind: Literal["field_mapping", "entity_grain", "record_match"]
    source_id: str
    source_field: str | None = None
    left_record: str | None = None
    right_record: str | None = None
    target: str
    score: float = Field(ge=0, le=1)
    disposition: Literal["accepted", "review", "rejected"]
    evidence: list[Evidence]
    checks: list[Check]
    model: Literal["deterministic", "ml"] = "deterministic"


class MappingProposal(BaseModel):
    source_id: str
    source_field: str
    canonical_field: str
    disposition: Literal["accepted", "review"]
    hypothesis_id: str


class ValueNormalizationProposal(Contract):
    proposal_id: str
    source_id: str
    source_field: str
    canonical_field: str
    record_key: str
    row_number: int
    raw_value: str
    proposed_value: str | None
    operation: Literal["trim", "casefold", "alias_lookup", "category_equivalence", "parse_date_de", "parse_decimal_de"]
    candidates: list[str] = Field(default_factory=list)
    evidence: list[Evidence]
    checks: list[Check]
    score: float = Field(ge=0, le=1)
    disposition: Literal["accepted", "review", "rejected"]
    recipe_candidate: dict[str, Any]


class RecipeDraft(Contract):
    recipe_id: str
    generated_by: str = "marble-discovery-0.0.1"
    mappings: list[MappingProposal]
    entity_grains: dict[str, str]
    # No merging or rewriting source records is authorized by a recipe draft.
    resolution_policy: Literal["no_merges"] = "no_merges"
    requires_review: bool = True
    normalization_proposal_ids: list[str] = Field(default_factory=list)


class CanonicalPreview(BaseModel):
    source_id: str
    record_key: str
    canonical_fields: dict[str, str | None]
    unmapped_fields: dict[str, str | None]


class InspectionReport(Contract):
    run_id: str
    source_profiles: list[SourceProfile]
    hypotheses: list[Hypothesis]
    recipe_draft: RecipeDraft
    canonical_preview: list[CanonicalPreview]
    metrics: dict[str, Any]
    normalization_proposals: list[ValueNormalizationProposal] = Field(default_factory=list)

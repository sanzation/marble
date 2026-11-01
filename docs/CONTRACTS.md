# Input and Output Contracts · Marble discovery v0.0.2

## SourceBatch (in memory)

Each CSV adapter returns a Pydantic `SourceBatch` with `schema_version=1`, `source_id`, `uri`, `columns`, and `records`. Every `SourceRecord` has a `source_id`, content-based `record_key`, physical `row_number` (ending line for multiline CSV records, including a preamble), `content_hash`, and `values: dict[str,str|null]`. **Do not normalise values in the ingestion adapter.**

The optional `batch.to_arrow()` returns `pyarrow.Table`, retaining original columns plus `_source_id`, `_record_key`, `_content_hash`. This is the intended later integration boundary for Polars and DuckDB execution. Installing `pyarrow` is optional for the current prototype.

## JSON documents

`report.json` is a Pydantic `InspectionReport` v1, emitted in deterministic order. Its subdocuments are `source_profiles.json`, `hypotheses.json`, `recipe_draft.json` and `canonical_preview.json`. JSON Schemas generated from the authoritative models are in `schemas/`. These outputs are *discovery artifacts*, not approved materialised canonical entities.

### Hypothesis

`hypothesis_id`, `kind` (field_mapping, entity_grain, record_match), `source_id`, `source_field` where relevant, `left_record/right_record` where relevant, `target`, `score`, `disposition`, `evidence[]`, `checks[]`, `model` (currently deterministic). A `Check` documents `name`, `passed`, `result`, and optional numeric `observed`.

**Important:** `accepted` is a positive rule outcome, not an expert confirmation or license to merge. `review` means ambiguous. `rejected` means a candidate failed the validation rule. Rejected candidates remain visible in reports.

### RecipeDraft

`recipe_id`, `generated_by`, `mappings[]`, `entity_grains`, `resolution_policy='no_merges'`, `requires_review=true`. Each proposed mapping points back to its hypothesis ID and carries its own disposition. The recipe draft does not execute data transforms or record-level merges.

## DuckDB schema (optional runtime adapter)

`source_records(source_id,record_key,row_number,content_hash,raw_json)`; `source_profiles(source_id,profile_json)`; `hypotheses(hypothesis_id,kind,source_id,target,score,disposition,evidence_json)`; `recipe_drafts(recipe_id,recipe_json)`; `run_reports(run_id,report_json)`.

The DuckDB adapter is behind the `InspectionStore` protocol. The in-memory discovery core cannot import DuckDB and may run without DuckDB using `--no-db`.

## Next version's contract changes

A stable user-provided primary key, explicit `SourceSpec`, approved recipes, compiled transforms, formal `Entity` / `Assertion` / `Fact` interfaces, and versioned (incremental) output are deferred until the hypothesis engine is proven. Changes to v1 contract must be additive or accompanied by schema-version migration.

## v0.0.2 additive fields and proposals

`SourceBatch` and `SourceProfile` have optional `ingestion` evidence with encoding,
delimiter, preamble count, ignored unused trailing header cells and parser-choice
details. Strict UTF-8/UTF-8 BOM decoding precedes strict cp1252 fallback; no
replacement characters are inserted. Standard doubled-quote escaping stays active
even if the short delimiter sample contains no escaped quotes. Empty trailing
headers are only ignored if no corresponding data cell exists; extra data still
raises an error. No source cell is silently dropped.

Optional `license`, `license_url`, `publisher`, `retrieved_at`, `declared_crs`
are validated and passed through from `inspect_csvs(source_metadata={source_id:
metadata})` or `--source-metadata file.json`. Provenance never changes semantic
decisions. Source IDs are CSV filename stems.

`InspectionReport.normalization_proposals` defaults to `[]` for old reports.
Each `ValueNormalizationProposal` has `schema_version=1`, `proposal_id`,
`source_id`, `source_field`, `canonical_field`, `record_key`, `row_number`,
`raw_value`, nullable `proposed_value`, `operation`, `candidates[]`, `evidence[]`,
`checks[]`, `score`, `disposition`, and non-executable `recipe_candidate`.

Operations: `trim` (including whitespace collapse), `casefold` (comparison with
an observed equivalent representative, not title-case inference), `alias_lookup`,
`category_equivalence`, `parse_date_de`, `parse_decimal_de`. A proposal can refer
to a trimmed value or extracted street token; `original_source_cell` evidence
retains the full unchanged input cell. This does not approve splitting composite
addresses in the schema or preview. Ambiguous aliases retain all candidates and
`proposed_value=null`. Approximate category equivalences always require review.
Invalid calendar dates are rejected; ambiguous day/month ordering requires
review. Numeric formatting never declares or transforms a CRS.

Alias packs are explicit local JSON via `alias_packs` / repeatable `--alias-pack`.
They validate against `AliasPack.schema.json`; no executable rules are accepted.
Aliases obey token boundaries and `field_scope`. Ambiguous entries require
exactly one explicit `school_type_in` rule matching the unchanged same-row school
type. Entity-match hypotheses are never normalization evidence. Conflicting
active packs produce `review`. Without a pack, there are no alias/category
proposals. `accepted` always means heuristically accepted, never human confirmed.

The school module contains an explicit vocabulary, not generic schema learning.
Composite addresses, name parts, operator/legal-form semantics and coordinates
require review. School candidates include within-source duplicates. Conflicting
IDs prevent acceptance; incompatible postal codes or cities are negative
evidence. No shared cross-state ID namespace is assumed.

`RecipeDraft.normalization_proposal_ids` is an additive list of references, default
`[]`. Additional exports: `normalization_proposals.json` and `.csv`.
`marble explain --kind normalization --id norm-...` exposes values, candidates,
evidence and checks. Run IDs include engine version, content, active packs and
metadata; proposal IDs include record, operation and rule evidence. No proposal
is executed. DuckDB stores the full extended report in `run_reports`.

Regenerate schemas: `python scripts/export_schemas.py`. Old sample reports remain
readable. JSON exports are checked against JSON Schema Draft 2020-12 in tests.

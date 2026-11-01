# Input and Output Contracts · Marble discovery v0.0.1

## SourceBatch (in memory)

Each CSV adapter returns a Pydantic `SourceBatch` with `schema_version=1`, `source_id`, `uri`, `columns`, and `records`. Every `SourceRecord` has a `source_id`, content-based `record_key`, physical `row_number`, `content_hash`, and `values: dict[str,str|null]`. **Do not normalise values in the ingestion adapter.**

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

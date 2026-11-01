from pathlib import Path
import json
import pytest
from marble import inspect_csvs
from marble.ingest import load_csv
from marble.models import InspectionReport, SourceBatch

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples' / 'three_csv'
FILES = [EXAMPLES / x for x in ['dcc_register.csv','council_extract.csv','gis_sites.csv']]


def test_three_csv_vertical_slice(tmp_path):
    report = inspect_csvs(FILES, output_dir=tmp_path)
    assert isinstance(report, InspectionReport)
    assert report.metrics['sources'] == 3
    assert report.metrics['source_records'] == 12
    assert report.metrics['actual_entities_merged'] == 0
    assert len(report.canonical_preview) == 12
    assert set(report.recipe_draft.entity_grains.values()) == {'site'}
    assert report.recipe_draft.resolution_policy == 'no_merges'
    assert (tmp_path/'hypotheses.csv').is_file()
    assert (tmp_path/'recipe_draft.json').is_file()
    assert (tmp_path/'report.json').is_file()
    assert json.loads((tmp_path/'report.json').read_text())['schema_version'] == 1
    assert all(h.checks and h.evidence for h in report.hypotheses)


def test_proposed_mappings_and_uncertainties():
    report = inspect_csvs(FILES)
    mappings = {(h.source_id,h.source_field,h.target): h for h in report.hypotheses if h.kind == 'field_mapping'}
    assert mappings['dcc_register','Reg ID','register_id'].disposition == 'accepted'
    assert mappings['dcc_register','Site Address','address'].disposition == 'accepted'
    assert mappings['council_extract','Location','address'].disposition == 'review'
    assert mappings['gis_sites','Reference','register_id'].disposition == 'review'
    assert mappings['gis_sites','State','status'].disposition == 'review'
    # Every proposal carries check results rather than a single unexplained score.
    assert {c.name for c in mappings['council_extract','Location','address'].checks} >= {
        'header_is_plausible','values_fit_target','cross_source_overlap'}
    assert all(p.disposition != 'rejected' for p in report.recipe_draft.mappings)


def test_wrong_merge_is_rejected_despite_address_similarity():
    report = inspect_csvs(FILES)
    rejected = [h for h in report.hypotheses if h.kind == 'record_match' and h.disposition == 'rejected']
    assert rejected, 'different site IDs with similar addresses should be negative evidence'
    assert any(any(c.name == 'no_id_conflict' and not c.passed for c in h.checks) for h in rejected)
    # Strong same-ID matches are hypotheses only, never actual merges.
    assert any(h.kind == 'record_match' and h.disposition == 'accepted' for h in report.hypotheses)
    assert report.metrics['actual_entities_merged'] == 0


def test_preview_never_drops_unapproved_fields():
    report = inspect_csvs(FILES)
    gis = next(r for r in report.canonical_preview if r.source_id == 'gis_sites')
    # Ambiguous fields are left in unmapped_fields, preserving raw data.
    assert gis.unmapped_fields.get('Reference') == 'DCC-101'
    assert gis.unmapped_fields.get('State') == 'Active'
    assert gis.canonical_fields['address'] == '12 Main Street'


def test_repeated_run_is_identical(tmp_path):
    first = inspect_csvs(FILES, output_dir=tmp_path)
    content = (tmp_path/'report.json').read_bytes()
    second = inspect_csvs(FILES, output_dir=tmp_path)
    assert first.run_id == second.run_id
    assert (tmp_path/'report.json').read_bytes() == content


def test_type_mismatch_rejects_mapping(tmp_path):
    bad = tmp_path/'dates.csv'
    bad.write_text('Date Added,Site Address,Reg ID\nnot-a-date,4 North Street,R-1\n', encoding='utf8')
    report = inspect_csvs([bad, FILES[0]])
    hypothesis = next(h for h in report.hypotheses if h.kind == 'field_mapping' and
                      h.source_id == 'dates' and h.source_field == 'Date Added' and h.target == 'recorded_date')
    assert hypothesis.disposition == 'rejected'
    assert any(c.name == 'values_fit_target' and not c.passed for c in hypothesis.checks)


def test_extra_csv_cells_are_not_silently_truncated(tmp_path):
    path = tmp_path/'bad.csv'
    path.write_text('a,b\nx,y,z\n', encoding='utf8')
    with pytest.raises(ValueError):
        load_csv(path)


def test_arrow_contract_opt_in():
    batch = load_csv(FILES[0])
    assert isinstance(batch, SourceBatch)
    assert len(batch.records) == 4
    assert batch.schema_version == 1
    assert batch.records[0].content_hash


def test_identical_csv_rows_keep_distinct_record_keys(tmp_path):
    duplicate = tmp_path/'twice.csv'
    duplicate.write_text('Reg ID,Site Address\nA-1,1 Main Street\nA-1,1 Main Street\n', encoding='utf8')
    batch = load_csv(duplicate)
    assert len(batch.records) == 2
    assert batch.records[0].record_key != batch.records[1].record_key
    assert batch.records[0].content_hash == batch.records[1].content_hash

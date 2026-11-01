"""Externally labelled synthetic fixtures: measurable baseline, not just smoke tests."""
import json
from pathlib import Path
from itertools import combinations
from marble import inspect_csvs
from marble.ingest import load_csv

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'examples'/'three_csv'


def test_labelled_record_matching_baseline():
    truth = json.loads((BASE/'truth.json').read_text())
    files = [BASE / f'{name}.csv' for name in truth['source_identifier_columns']]
    batches = [load_csv(f) for f in files]
    record_to_entity = {}
    for batch in batches:
        col = truth['source_identifier_columns'][batch.source_id]
        for record in batch.records:
            record_to_entity[batch.source_id + ':' + record.record_key] = record.values[col]
    all_positive_pairs = {
        frozenset((a,b)) for a,b in combinations(record_to_entity, 2)
        if a.split(':',1)[0] != b.split(':',1)[0]
        and record_to_entity[a] == record_to_entity[b]
    }
    assert len(all_positive_pairs) == truth['expected_same_entity_pairs']
    report = inspect_csvs(files)
    accepted_pairs = {
        frozenset((h.left_record, h.right_record))
        for h in report.hypotheses
        if h.kind == 'record_match' and h.disposition == 'accepted'
    }
    true_positives = len(all_positive_pairs & accepted_pairs)
    precision = true_positives / len(accepted_pairs) if accepted_pairs else 0
    recall = true_positives / len(all_positive_pairs) if all_positive_pairs else 0
    # This is a tiny, purposely simple regression fixture, NOT performance proof.
    assert precision == 1.0
    assert recall == 1.0
    assert accepted_pairs == all_positive_pairs


def test_expected_schema_labels_are_present():
    truth = json.loads((BASE/'truth.json').read_text())
    report = inspect_csvs([BASE / f'{name}.csv' for name in truth['source_identifier_columns']])
    candidates = {(h.source_id, h.source_field, h.target)
                  for h in report.hypotheses
                  if h.kind == 'field_mapping' and h.disposition != 'rejected'}
    for source, mapping in truth['expected_mappings'].items():
        for field, target in mapping.items():
            assert (source, field, target) in candidates


def test_repeated_identifier_demotes_automatic_acceptance(tmp_path):
    malformed = tmp_path/'repeated.csv'
    malformed.write_text('Reg ID,Site Address\nA-1,1 Main Street\nA-1,2 Main Street\n', encoding='utf8')
    report = inspect_csvs([malformed, BASE/'dcc_register.csv'])
    h = next(h for h in report.hypotheses if h.kind == 'field_mapping'
             and h.source_id == 'repeated' and h.source_field == 'Reg ID'
             and h.target == 'register_id')
    assert h.disposition == 'review'
    assert any(c.name == 'identifier_is_unique_in_source' and not c.passed for c in h.checks)

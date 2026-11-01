"""Runs after normal installation; gracefully skipped in offline stdlib-only audits."""
from pathlib import Path
import pytest
from marble import inspect_csvs

pytest.importorskip('duckdb')

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'examples'/'three_csv'
FILES = [BASE/f for f in ['dcc_register.csv','council_extract.csv','gis_sites.csv']]


def test_duckdb_snapshot_and_idempotent_replacement(tmp_path):
    import duckdb
    db = tmp_path/'inspection.duckdb'
    report = inspect_csvs(FILES, duckdb_path=db)
    con = duckdb.connect(str(db))
    try:
        assert con.execute('select count(*) from source_records').fetchall() == [(12,)]
        assert con.execute('select count(*) from hypotheses').fetchall() == [(len(report.hypotheses),)]
    finally:
        con.close()
    inspect_csvs(FILES, duckdb_path=db)
    con = duckdb.connect(str(db))
    try:
        assert con.execute('select count(*) from source_records').fetchall() == [(12,)]
        assert con.execute('select count(*) from recipe_drafts').fetchall() == [(1,)]
    finally:
        con.close()

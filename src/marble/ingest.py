"""CSV-only adapter v0.0.1. Never coerces or discards source values."""
from __future__ import annotations
import csv
import hashlib
import io
import json
from pathlib import Path
from .models import CSVIngestion, SourceBatch, SourceRecord


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def load_csv(path: str | Path, source_id: str | None = None) -> SourceBatch:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    sid = source_id or path.stem
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
        encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
        encoding = "cp1252"
    # Excel's sep= preamble is metadata, never a source record or column.
    first_line, _, remainder = text.partition("\n")
    declared_delimiter = first_line.removeprefix("sep=").strip() if first_line.startswith("sep=") else None
    preamble_lines = 1 if declared_delimiter in {",", ";", "\t", "|"} else 0
    if preamble_lines:
        text = remainder
    with io.StringIO(text, newline="") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        delimiter = declared_delimiter if preamble_lines and declared_delimiter is not None else dialect.delimiter
        # A sample without escaped quotes makes Sniffer infer doublequote=False.
        # Later records still use standard CSV doubled-quote escaping.
        reader = csv.DictReader(fh, dialect=dialect, delimiter=delimiter, doublequote=True)
        columns = list(reader.fieldnames or [])
        if not columns:
            raise ValueError(f"No CSV header: {path}")
        # The official NRW export has one empty trailing header, but no
        # corresponding data column. Accept only that precise shape, and log it.
        ignored_empty_header_columns = 0
        if columns[-1] == "" and all(columns[:-1]):
            columns.pop()
            reader.fieldnames = columns
            ignored_empty_header_columns = 1
        if not columns or len(columns) != len(set(columns)) or any(not x for x in columns):
            raise ValueError(f"Duplicate/empty CSV column names are unsupported: {path}")
        rows: list[SourceRecord] = []
        occurrence_by_hash: dict[str, int] = {}
        for row in reader:
            line_no = reader.line_num + preamble_lines
            if None in row:
                raise ValueError(f"Extra CSV values in {path}, row {line_no}")
            values = {col: row[col] for col in columns}
            if all(v is None or not v.strip() for v in values.values()):
                continue
            content_hash = _digest(values)
            occurrence = occurrence_by_hash.get(content_hash, 0) + 1
            occurrence_by_hash[content_hash] = occurrence
            # Stable for unchanged unique row content. Duplicate identical rows
            # get occurrence suffixes; without a primary key, reorders/edits
            # cannot be tracked robustly (explicit limitation of MVP).
            rows.append(SourceRecord(source_id=sid, record_key=f"sha256:{content_hash[:20]}:{occurrence}", row_number=line_no,
                                     content_hash=content_hash, values=values))
    ingestion = CSVIngestion(encoding=encoding, delimiter=delimiter, preamble_lines=preamble_lines,
                             ignored_empty_header_columns=ignored_empty_header_columns,
                             evidence=[f"strict decoding: {encoding}",
                                       "delimiter declared by sep= preamble" if preamble_lines else "delimiter selected by CSV Sniffer or comma fallback",
                                       "standard CSV doubled-quote escaping enabled",
                                       "UTF-8/cp1252 selection is a decoding heuristic, not an encoding declaration"])
    return SourceBatch(source_id=sid, uri=path.as_posix(), columns=columns, records=rows, ingestion=ingestion)

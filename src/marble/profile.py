from __future__ import annotations
from .models import ColumnProfile, SourceBatch, SourceMetadata, SourceProfile
from .semantics import pattern


def profile_batch(batch: SourceBatch) -> SourceProfile:
    col_profiles = []
    size = len(batch.records)
    for col in batch.columns:
        values = [r.values.get(col, "") or "" for r in batch.records]
        nonempty = [v.strip() for v in values if v.strip()]
        distinct = list(dict.fromkeys(nonempty))
        col_profiles.append(ColumnProfile(
            name=col, nonempty=len(nonempty), distinct_nonempty=len(distinct),
            completeness=round(len(nonempty)/size, 4) if size else 0,
            uniqueness=round(len(distinct)/len(nonempty), 4) if nonempty else 0,
            sample_values=distinct[:5], detected_pattern=pattern(nonempty[:100])
        ))
    return SourceProfile(source_id=batch.source_id, uri=batch.uri,
                         record_count=size, columns=col_profiles, ingestion=batch.ingestion,
                         **SourceMetadata.model_validate({key: getattr(batch, key) for key in SourceMetadata.model_fields}).model_dump())

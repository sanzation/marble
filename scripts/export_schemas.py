"""Regenerate the checked-in JSON schemas from the authoritative models."""
import json
from pathlib import Path

from marble.models import (
    CanonicalPreview, Hypothesis, InspectionReport, RecipeDraft, SourceBatch,
    SourceProfile, ValueNormalizationProposal,
)
from marble.normalization import AliasPack

MODELS = (CanonicalPreview, Hypothesis, InspectionReport, RecipeDraft,
          SourceBatch, SourceProfile, ValueNormalizationProposal, AliasPack)


def main():
    output = Path(__file__).resolve().parents[1] / "docs" / "schemas"
    for model in MODELS:
        (output / f"{model.__name__}.schema.json").write_text(
            json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

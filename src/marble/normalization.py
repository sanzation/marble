"""Candidate generation and explicit validation; suggestions never rewrite cells."""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import Check, Evidence, SourceBatch, SourceRecord, ValueNormalizationProposal
from .schools import column_roles


class PackContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContextRule(PackContract):
    school_type_in: list[str]


class AliasCandidate(PackContract):
    canonical: str
    context_rule: ContextRule | None = None


class AliasEntry(PackContract):
    surface: str = Field(min_length=1)
    field_scope: list[str]
    ambiguous: bool
    canonical: str | None = None
    candidates: list[AliasCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_choice(self):
        if self.ambiguous and len(self.candidates) < 2:
            raise ValueError("Ambiguous aliases need at least two candidates")
        if not self.ambiguous and not self.canonical:
            raise ValueError("Unambiguous aliases need a canonical value")
        return self


class AddressRule(PackContract):
    rule: str
    pattern: str = Field(min_length=1)
    canonical: str
    field_scope: list[str]


class CategoryEquivalence(PackContract):
    group: str
    members: list[str]
    strength: Literal["approximate"]
    note: str


class AliasPack(PackContract):
    pack_id: str
    pack_version: str
    status: str
    note: str
    entries: list[AliasEntry]
    address_rules: list[AddressRule] = Field(default_factory=list)
    category_equivalences: list[CategoryEquivalence] = Field(default_factory=list)


def load_alias_packs(paths: Sequence[str | Path]) -> list[AliasPack]:
    packs = [AliasPack.model_validate_json(Path(path).read_text(encoding="utf-8")) for path in paths]
    if len({pack.pack_id for pack in packs}) != len(packs):
        raise ValueError("Alias pack IDs must be unique")
    return sorted(packs, key=lambda pack: pack.pack_id)


def _surface_pattern(surface: str) -> str:
    return r"(?<!\w)" + re.escape(surface) + r"(?!\w)"


def _replace(pattern: str, canonical: str, value: str) -> str:
    return re.sub(pattern, lambda _: canonical, value, flags=re.IGNORECASE)


def _street_part(value: str) -> str:
    segment = value.split(",", 1)[0].strip()
    match = re.fullmatch(r"(.+?\D)\s*(\d+[A-Za-z]?)", segment)
    return match.group(1).strip() if match else segment


def _cells(batch: SourceBatch, record: SourceRecord):
    for column, role in column_roles(batch).items():
        raw = record.values.get(column)
        if not raw:
            continue
        yield column, role, raw
        if role == "street_address" and column != "Hausnummer":
            yield column, "street", _street_part(raw)


def _proposal(batch: SourceBatch, record: SourceRecord, column: str, role: str, raw: str,
              proposed: str | None, operation: str, evidence: list[Evidence], checks: list[Check],
              *, candidates: list[str] | None = None) -> ValueNormalizationProposal:
    """Validation is independent of candidate generation and record matching."""
    accepted = all(check.passed for check in checks)
    disposition = "accepted" if accepted else "review"
    payload = [batch.source_id, record.record_key, column, role, raw, proposed, operation,
               candidates or [], [e.model_dump() for e in evidence]]
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    return ValueNormalizationProposal.model_validate({
        "proposal_id": "norm-" + digest, "source_id": batch.source_id, "source_field": column,
        "canonical_field": role, "record_key": record.record_key, "row_number": record.row_number,
        "raw_value": raw, "proposed_value": proposed, "operation": operation,
        "candidates": candidates or [], "disposition": disposition, "score": .95 if accepted else .5,
        "evidence": [*evidence, Evidence(signal="original_source_cell", strength=1,
                                        detail=record.values.get(column) or "")],
        "checks": [*checks, Check(name="discovery_only", passed=True,
                                  result="Heuristically accepted is not human confirmed; no value is written")],
        "recipe_candidate": {"operation": operation, "source_field": column, "canonical_field": role,
                             "record_key": record.record_key, "proposed_value": proposed,
                             "requires_review": True}})


def _format_proposals(batch: SourceBatch, record: SourceRecord, column: str, role: str,
                      raw: str) -> list[ValueNormalizationProposal]:
    if role == "as_of_date" and re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", raw):
        try:
            target = datetime.strptime(raw, "%d.%m.%Y").date().isoformat()
        except ValueError:
            target = None
        proposal = _proposal(batch, record, column, role, raw, target, "parse_date_de",
            [Evidence(signal="explicit_date_shape", strength=1, detail="dd.mm.yyyy candidate; no locale assumed from entity matching")],
            [Check(name="valid_calendar_date", passed=target is not None, result="Calendar validation"),
             Check(name="day_first_unambiguous", passed=int(raw[:2]) > 12,
                   result="Day > 12 rules out month-first interpretation; ambiguous dates remain review")])
        if target is None:
            proposal.disposition, proposal.score = "rejected", 0
        return [proposal]
    if role in {"easting", "northing"} and re.fullmatch(r"[+-]?\d+,\d+", raw):
        return [_proposal(batch, record, column, "easting/northing", raw, raw.replace(",", "."), "parse_decimal_de",
            [Evidence(signal="decimal_comma_shape", strength=1, detail="Single decimal comma; no grouping separators; no CRS transformation")],
            [Check(name="unambiguous_decimal_format", passed=True, result="Only numeric formatting is proposed; CRS remains a separate review")])]
    return []


def discover_normalizations(batches: list[SourceBatch], packs: list[AliasPack]) -> list[ValueNormalizationProposal]:
    cells = [(batch, record, column, role, raw) for batch in batches for record in batch.records
             for column, role, raw in _cells(batch, record)]
    variants: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for _, _, _, role, raw in cells:
        variants[(role, raw.strip().casefold())][raw.strip()] += 1
    proposals = []
    for batch, record, column, role, original in cells:
        raw = re.sub(r"\s+", " ", original.strip())
        proposals.extend(_format_proposals(batch, record, column, role, raw))
        if raw != original:
            proposals.append(_proposal(batch, record, column, role, original, raw, "trim",
                [Evidence(signal="whitespace_only", strength=1, detail="Trim and collapse whitespace; non-whitespace characters unchanged")],
                [Check(name="only_whitespace_changes", passed=True, result="No lexical replacement")]))
        equivalent = variants[(role, raw.casefold())]
        anchor = min(equivalent, key=lambda value: (-equivalent[value], value.islower(), value)) if equivalent else raw
        if anchor != raw and anchor.casefold() == raw.casefold():
            proposals.append(_proposal(batch, record, column, role, raw, anchor, "casefold",
                [Evidence(signal="observed_casefold_equivalent", strength=1,
                          detail=f"Observed representative {anchor!r}; casefold comparison is not title-case inference")],
                [Check(name="casefold_equal", passed=True, result="Both observed values have the same casefold")]))
        for pack in packs:
            pack_evidence = Evidence(signal="active_alias_pack", strength=1,
                                     detail=f"{pack.pack_id}@{pack.pack_version}; explicitly activated, field-scoped")
            for entry in pack.entries:
                pattern = _surface_pattern(entry.surface)
                if role not in entry.field_scope or not re.search(pattern, raw, re.IGNORECASE):
                    continue
                choices = [_replace(pattern, candidate.canonical, raw) for candidate in entry.candidates]
                chosen = [candidate for candidate in entry.candidates if candidate.context_rule is not None
                          and any(record.values.get(c) in candidate.context_rule.school_type_in
                                  for c, r in column_roles(batch).items() if r == "school_type")]
                resolved = not entry.ambiguous or len(chosen) == 1
                target = chosen[0].canonical if entry.ambiguous and len(chosen) == 1 else entry.canonical if not entry.ambiguous else None
                proposed = _replace(pattern, target, raw) if target is not None else None
                proposals.append(_proposal(batch, record, column, role, raw, proposed, "alias_lookup",
                    [pack_evidence, Evidence(signal="alias_candidates", strength=.9,
                                              detail=json.dumps(choices, ensure_ascii=False) if entry.ambiguous else f"Explicit entry {entry.surface} -> {entry.canonical}")],
                    [Check(name="field_scope", passed=role in entry.field_scope, result=f"Explicit scope: {entry.field_scope}"),
                     Check(name="ambiguity_resolved_by_raw_context", passed=resolved,
                           result="Unambiguous curated entry" if not entry.ambiguous else
                           "Exactly one context_rule matches the same raw row" if resolved else
                           "No unique explicit raw-row context; entity-match hypotheses are not used")],
                    candidates=choices if not resolved else []))
            for rule in pack.address_rules:
                pattern = re.escape(rule.pattern) + r"(?=$|\s)"
                if role in rule.field_scope and re.search(pattern, raw, re.IGNORECASE):
                    proposals.append(_proposal(batch, record, column, role, raw,
                        _replace(pattern, rule.canonical, raw), "alias_lookup", [pack_evidence],
                        [Check(name="field_scope", passed=True, result=f"Explicit address rule {rule.rule}; source component retained as evidence")]))
            for category in pack.category_equivalences:
                if role == "school_type" and raw in category.members:
                    proposals.append(_proposal(batch, record, column, role, raw, category.group, "category_equivalence",
                        [pack_evidence, Evidence(signal="approximate_category", strength=.5, detail=category.note)],
                        [Check(name="exact_category_identity", passed=False, result="Approximate grouping across state law; requires review")]))
    # Multiple activated packs may disagree. Never accept competing targets for
    # the same input, even if each rule is unambiguous in isolation.
    groups: dict[tuple[str, str, str, str, str], list[ValueNormalizationProposal]] = defaultdict(list)
    for proposal in proposals:
        groups[(proposal.source_id, proposal.record_key, proposal.canonical_field,
                proposal.operation, proposal.raw_value)].append(proposal)
    for group in groups.values():
        targets = {p.proposed_value for p in group if p.operation == "alias_lookup"}
        if len(targets) > 1:
            for proposal in group:
                proposal.disposition, proposal.score = "review", .5
                proposal.checks.append(Check(name="active_rules_agree", passed=False,
                                             result="Activated alias packs propose competing targets"))
    return sorted(proposals, key=lambda p: (p.source_id, p.row_number, p.source_field, p.operation, p.proposal_id))

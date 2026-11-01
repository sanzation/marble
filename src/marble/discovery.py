"""Explainable rule-based hypothesis generation. Deliberately no implicit merges."""
from __future__ import annotations
import hashlib
from difflib import SequenceMatcher
from itertools import combinations
from .models import (
    Check, Evidence, Hypothesis, MappingProposal, RecipeDraft,
    SourceBatch, SourceProfile, CanonicalPreview,
)
from .semantics import FIELD_ALIASES, header_similarity, normalize_value, value_compatible
from .schools import column_roles, discover_school_fields, discover_school_matches


def _id(*parts: str) -> str:
    key = "|".join(parts).encode("utf8")
    return "hyp-" + hashlib.sha256(key).hexdigest()[:16]


def _column_data(batch: SourceBatch, col: str) -> list[str]:
    return [value for record in batch.records if (value := (record.values.get(col) or "").strip())]


def _overlap(batches: list[SourceBatch], batch: SourceBatch, col: str, field: str) -> float:
    a = {normalize_value(x, field) for x in _column_data(batch, col)}
    if not a:
        return 0.0
    others: set[str] = set()
    for other in batches:
        if other.source_id == batch.source_id:
            continue
        candidates = [c for c in other.columns if header_similarity(c, field) >= .65]
        for c in candidates:
            others.update(normalize_value(x, field) for x in _column_data(other, c))
    if not others:
        return 0.0
    return len(a & others) / max(1, min(len(a), len(others)))


def discover_field_hypotheses(batches: list[SourceBatch]) -> list[Hypothesis]:
    proposals = discover_school_fields(batches)
    for batch in batches:
        school_roles = column_roles(batch)
        for col in batch.columns:
            if col in school_roles:
                continue
            ranked = sorted(((t, header_similarity(col, t)) for t in FIELD_ALIASES), key=lambda x: -x[1])
            # A hypothesis needs at least a weak lexical signal. Unknown columns
            # intentionally remain unclassified, never silently discarded.
            for target, header_score in ranked[:2]:
                if header_score < .48:
                    continue
                vals = _column_data(batch, col)
                type_support = sum(value_compatible(v, target) for v in vals) / len(vals) if vals else 0.0
                overlap = _overlap(batches, batch, col, target)
                score = round(.62 * header_score + .23 * type_support + .15 * overlap, 3)
                uniqueness = len(set(vals)) / len(vals) if vals else 0.0
                checks = [
                    Check(name="header_is_plausible", passed=header_score >= .65,
                          observed=round(header_score, 3), result="lexical alias match; not semantic certainty"),
                    Check(name="values_fit_target", passed=type_support >= .8,
                          observed=round(type_support, 3), result=f"{sum(value_compatible(v, target) for v in vals)}/{len(vals)} observed values compatible"),
                    Check(name="sufficient_coverage", passed=len(vals) >= max(1, len(batch.records)//2),
                          observed=round(len(vals)/max(1, len(batch.records)), 3), result="non-null values / source rows"),
                    Check(name="cross_source_overlap", passed=overlap >= .25,
                          observed=round(overlap, 3), result="normalized values shared with similar fields; supporting evidence only"),
                    Check(name="identifier_is_unique_in_source", passed=target != "register_id" or uniqueness >= .95,
                          observed=round(uniqueness, 3), result="identifier uniqueness expected for a one-row-per-site source; repeated IDs require grain review"),
                ]
                if not checks[1].passed or header_score < .60:
                    disposition = "rejected"
                elif header_score >= .90 and score >= .77 and checks[2].passed and checks[4].passed:
                    disposition = "accepted"
                else:
                    disposition = "review"
                proposals.append(Hypothesis(
                    hypothesis_id=_id("field", batch.source_id, col, target), kind="field_mapping",
                    source_id=batch.source_id, source_field=col, target=target, score=score,
                    disposition=disposition,
                    evidence=[Evidence(signal="column_name", strength=header_score,
                                       detail=f"'{col}' resembles semantic field '{target}'"),
                              Evidence(signal="value_pattern", strength=round(type_support,3),
                                       detail=f"sample values compatible with '{target}'"),
                              Evidence(signal="other_sources", strength=round(overlap,3),
                                       detail="cross-source normalized value overlap")],
                    checks=checks,
                ))
    return proposals


def discover_entity_grains(batches: list[SourceBatch], mappings: list[Hypothesis]) -> list[Hypothesis]:
    results = []
    for batch in batches:
        matched_fields = {h.target for h in mappings if h.source_id == batch.source_id and h.disposition != "rejected"}
        tests = {
            "site": [("has_address_or_geo", "address" in matched_fields or {"latitude","longitude"}.issubset(matched_fields)),
                     ("has_record_identifier", "register_id" in matched_fields),
                     ("has_context", "local_authority" in matched_fields or "status" in matched_fields)],
            "event": [("has_event_date", "event_date" in matched_fields),
                      ("has_event_action", "event_action" in matched_fields)],
            "organization": [("has_org_name", "organization_name" in matched_fields),
                             ("has_org_identifier", "organization_id" in matched_fields)],
        }
        if column_roles(batch):
            tests["school"] = [("has_school_name", "school_name" in matched_fields),
                               ("has_school_type", "school_type" in matched_fields)]
        for grain, required in tests.items():
            passed = sum(ok for _, ok in required)
            score = round(passed / len(required), 3)
            disposition = "accepted" if all(ok for _,ok in required) else "rejected"
            results.append(Hypothesis(
                hypothesis_id=_id("grain", batch.source_id, grain), kind="entity_grain",
                source_id=batch.source_id, target=grain, score=score, disposition=disposition,
                checks=[Check(name=n, passed=ok, result="schema provides supporting fields" if ok else "required fields not discovered")
                        for n, ok in required],
                evidence=[Evidence(signal="structural_signature", strength=score,
                                   detail=f"observed candidate fields: {', '.join(sorted(matched_fields))}")]
            ))
    return results


def _best_col(hypotheses: list[Hypothesis], source_id: str, target: str) -> str | None:
    candidates = [h for h in hypotheses if h.kind == "field_mapping" and
                  h.source_id == source_id and h.target == target and h.disposition != "rejected"]
    return max(candidates, key=lambda h: h.score).source_field if candidates else None


def discover_record_matches(batches: list[SourceBatch], field_hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """A few candidates for manual inspection; never persists entity links."""
    matches: list[Hypothesis] = discover_school_matches(batches)
    for left, right in combinations(batches, 2):
        l_id = _best_col(field_hypotheses, left.source_id, "register_id")
        r_id = _best_col(field_hypotheses, right.source_id, "register_id")
        l_addr = _best_col(field_hypotheses, left.source_id, "address")
        r_addr = _best_col(field_hypotheses, right.source_id, "address")
        for a in left.records:
            for b in right.records:
                av = normalize_value(a.values.get(l_id, "") or "", "register_id") if l_id else ""
                bv = normalize_value(b.values.get(r_id, "") or "", "register_id") if r_id else ""
                same_id = bool(av and bv and av == bv)
                id_conflict = bool(av and bv and av != bv)
                aa = normalize_value(a.values.get(l_addr, "") or "", "address") if l_addr else ""
                ba = normalize_value(b.values.get(r_addr, "") or "", "address") if r_addr else ""
                address_similarity = SequenceMatcher(None, aa, ba).ratio() if aa and ba else 0.0
                if not same_id and address_similarity < .75:
                    continue
                score = round(.73 * float(same_id) + .27 * address_similarity, 3)
                if id_conflict:
                    disposition = "rejected"
                elif same_id and address_similarity >= .70:
                    disposition = "accepted"  # Accepted hypothesis only, never an automatic merge.
                else:
                    disposition = "review"
                checks = [
                    Check(name="id_agreement", passed=same_id,
                          result=f"IDs: '{av or 'missing'}' versus '{bv or 'missing'}'"),
                    Check(name="no_id_conflict", passed=not id_conflict,
                          result="distinct identifiers must not be auto-merged" if id_conflict else "no contradictory IDs"),
                    Check(name="address_similarity", passed=address_similarity >= .70,
                          observed=round(address_similarity,3), result="normalized address similarity"),
                ]
                matches.append(Hypothesis(
                    hypothesis_id=_id("pair", left.source_id, a.record_key, right.source_id, b.record_key),
                    kind="record_match", source_id=f"{left.source_id}|{right.source_id}",
                    left_record=f"{left.source_id}:{a.record_key}",
                    right_record=f"{right.source_id}:{b.record_key}",
                    target="same_real_world_entity", score=score, disposition=disposition,
                    checks=checks,
                    evidence=[Evidence(signal="identifier_equal", strength=float(same_id),
                                       detail=f"{av or '<missing>'} vs {bv or '<missing>'}"),
                              Evidence(signal="address_similarity", strength=round(address_similarity,3),
                                       detail=f"{aa or '<missing>'} vs {ba or '<missing>'}")]
                ))
    return matches


def build_recipe_draft(batches: list[SourceBatch], hypotheses: list[Hypothesis]) -> RecipeDraft:
    proposals: list[MappingProposal] = []
    grains: dict[str, str] = {}
    for batch in batches:
        for col in batch.columns:
            candidates = [h for h in hypotheses if h.kind == "field_mapping" and h.source_id == batch.source_id
                          and h.source_field == col and h.disposition != "rejected"]
            if candidates:
                top = max(candidates, key=lambda h: h.score)
                if top.disposition != "rejected":
                    proposals.append(MappingProposal(source_id=batch.source_id, source_field=col,
                        canonical_field=top.target, disposition=top.disposition, hypothesis_id=top.hypothesis_id))
        types = [h for h in hypotheses if h.kind == "entity_grain" and h.source_id == batch.source_id
                 and h.disposition == "accepted"]
        if len(types) == 1:
            grains[batch.source_id] = types[0].target
    digest = hashlib.sha256("|".join(sorted(p.hypothesis_id for p in proposals)).encode()).hexdigest()[:16]
    return RecipeDraft(recipe_id=f"draft-{digest}", mappings=proposals, entity_grains=grains)


def make_preview(batches: list[SourceBatch], draft: RecipeDraft) -> list[CanonicalPreview]:
    """Preview *only* accepted mapping hypotheses. Never removes unmapped values."""
    approved = {(p.source_id, p.source_field): p.canonical_field
                for p in draft.mappings if p.disposition == "accepted"}
    preview: list[CanonicalPreview] = []
    for batch in batches:
        for row in batch.records:
            canonical = {}
            unmapped = {}
            for key,value in row.values.items():
                target = approved.get((batch.source_id, key))
                if target:
                    canonical[target] = value  # no value normalization until recipe is explicitly approved
                else:
                    unmapped[key] = value
            preview.append(CanonicalPreview(source_id=batch.source_id, record_key=row.record_key,
                                            canonical_fields=canonical, unmapped_fields=unmapped))
    return preview

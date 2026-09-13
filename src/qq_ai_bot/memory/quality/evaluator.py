"""Deterministic structured comparison; no model and no fuzzy scoring."""

from __future__ import annotations

from qq_ai_bot.memory.quality.models import (
    MemoryQualityCase,
    QualityCaseResult,
    QualityEvidenceSpec,
    QualityFactSpec,
    QualityObservation,
    QualityRelationSpec,
)


def fact_key(fact: QualityFactSpec) -> str:
    return "|".join(
        (
            fact.fact_ref,
            fact.scope_type,
            fact.subject or "-",
            fact.group or "-",
            fact.kind,
            fact.memory_key,
            fact.content,
            fact.status,
            fact.conflict_state,
            fact.authority,
        )
    )


def evidence_key(evidence: QualityEvidenceSpec) -> str:
    return "|".join(
        (
            evidence.fact_ref,
            evidence.event_ref,
            evidence.speaker,
            evidence.relation,
            evidence.excerpt,
        )
    )


def relation_key(relation: QualityRelationSpec) -> str:
    return "|".join((relation.source_fact_ref, relation.target_fact_ref, relation.relation_type))


class MemoryQualityEvaluator:
    """Compare stable symbolic keys and explicit forbidden sets."""

    def evaluate(
        self,
        case: MemoryQualityCase,
        observation: QualityObservation,
    ) -> QualityCaseResult:
        failures: list[str] = []
        self._exact("claims", set(case.expected_claims), set(observation.claims), failures)
        expected_facts = {fact_key(item) for item in case.expected_facts}
        self._exact("facts", expected_facts, set(observation.facts), failures)
        self._exact(
            "evidence",
            {evidence_key(item) for item in case.expected_evidence},
            set(observation.evidence),
            failures,
        )
        self._exact(
            "relations",
            {relation_key(item) for item in case.expected_relations},
            set(observation.relations),
            failures,
        )
        expected_retrieval = set(case.expected_retrieval)
        if not expected_retrieval:
            expected_retrieval = {
                f"{query.query_ref}|{fact_ref}"
                for query in case.queries
                for fact_ref in query.expected_fact_refs
            }
        self._exact("retrieval", expected_retrieval, set(observation.retrieval), failures)
        expected_context = set(case.expected_context)
        if not expected_context:
            expected_context = {
                f"{query.query_ref}|{fact_ref}"
                for query in case.queries
                if query.context
                for fact_ref in query.expected_fact_refs
            }
        self._exact("context", expected_context, set(observation.context), failures)
        for forbidden in case.forbidden_facts:
            if any(forbidden in item for item in observation.facts):
                failures.append(f"forbidden_fact:{forbidden}")
        for query in case.queries:
            for forbidden in query.forbidden_fact_refs:
                if f"{query.query_ref}|{forbidden}" in observation.retrieval:
                    failures.append(f"forbidden_retrieval:{query.query_ref}:{forbidden}")
        for forbidden in case.forbidden_context:
            if any(forbidden in item for item in observation.context):
                failures.append(f"forbidden_context:{forbidden}")
        if case.expected_rebuild != observation.rebuild:
            failures.append("rebuild:mismatch")
        if observation.error_code:
            failures.append(f"pipeline_error:{observation.error_code}")
        return QualityCaseResult(
            case_id=case.case_id,
            category=case.category,
            passed=not failures,
            failures=tuple(sorted(failures)),
            observation=observation,
        )

    @staticmethod
    def _exact(
        label: str,
        expected: set[str],
        observed: set[str],
        failures: list[str],
    ) -> None:
        for missing in sorted(expected - observed):
            failures.append(f"{label}:missing:{missing}")
        for unexpected in sorted(observed - expected):
            failures.append(f"{label}:unexpected:{unexpected}")

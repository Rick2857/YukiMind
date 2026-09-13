"""Deterministic Memory V2 quality metrics with explicit denominators."""

from __future__ import annotations

import math
import statistics
from collections import Counter

from qq_ai_bot.memory.quality.evaluator import evidence_key, fact_key
from qq_ai_bot.memory.quality.models import (
    MemoryQualityCase,
    QualityCaseResult,
    QualityMetricValue,
)


def ratio(numerator: float, denominator: float, *, unit: str = "ratio") -> QualityMetricValue:
    """Return ``null`` when there is no eligible sample; never invent a zero."""

    return QualityMetricValue(
        value=(numerator / denominator if denominator else None),
        numerator=numerator,
        denominator=denominator,
        unit=unit,
    )


def value(number: float | None, *, unit: str) -> QualityMetricValue:
    return QualityMetricValue(
        value=number,
        numerator=number if number is not None else 0,
        denominator=1 if number is not None else 0,
        unit=unit,
    )


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    # With fewer than 20 observations, nearest-rank p95 is just one maximum and is
    # dominated by scheduler noise rather than a useful tail-latency distribution.
    if quantile >= 0.95 and len(values) < 20:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1))
    return ordered[index]


def _claim_parts(key: str) -> tuple[str, str, str, str, str] | None:
    parts = key.split("|", 4)
    return tuple(parts) if len(parts) == 5 else None  # type: ignore[return-value]


def _evidence_parts(key: str) -> tuple[str, str, str, str, str] | None:
    parts = key.split("|", 4)
    return tuple(parts) if len(parts) == 5 else None  # type: ignore[return-value]


def _fact_parts(key: str) -> tuple[str, ...]:
    return tuple(key.split("|"))


class MemoryQualityMetrics:
    """Aggregate structured observations only; no text similarity and no model scoring."""

    def calculate(
        self,
        cases: tuple[MemoryQualityCase, ...],
        results: tuple[QualityCaseResult, ...],
    ) -> dict[str, QualityMetricValue]:
        by_id = {item.case_id: item for item in cases}

        expected_claim_count = 0
        correct_subject_count = 0
        correct_scope_count = 0
        expected_fact_count = 0
        exact_fact_count = 0
        expected_evidence_count = 0
        exact_evidence_count = 0
        observed_derived_fact_count = 0
        fact_without_evidence_count = 0
        evidence_count = 0
        duplicate_evidence_count = 0
        source_event_mismatch_count = 0
        outbound_evidence_count = 0
        bot_evidence_count = 0
        blank_evidence_count = 0
        outbound_event_count = 0
        bot_event_count = 0
        blank_event_count = 0
        active_slot_count = 0
        duplicate_active_fact_count = 0
        expected_state_count = 0
        correct_state_count = 0
        expected_retrieval_count = 0
        retrieved_count = 0
        relevant_retrieved = 0
        wrong_target_retrieval = 0
        reciprocal_ranks: list[float] = []
        ndcgs: list[float] = []
        expected_context_count = 0
        observed_context_count = 0
        relevant_context_count = 0
        wrong_subject_context = 0
        wrong_group_context = 0
        contested_context_leaks = 0
        third_party_misattributions = 0
        historical_cases = 0
        historical_failures = 0
        idempotency_cases = 0
        idempotency_failures = 0
        correction_cases = 0
        correction_passed = 0
        retraction_cases = 0
        retraction_passed = 0
        conflict_cases = 0
        conflict_passed = 0
        rebuild_cases = 0
        rebuild_review_bypasses = 0
        rebuild_duplicate_commits = 0
        rebuild_historical_overwrites = 0
        rebuild_receipt_correct = 0
        rebuild_resume_correct = 0
        rebuild_receipt_cases = 0
        rebuild_resume_cases = 0
        cross_person_denominator = 0
        cross_person_hits = 0
        cross_group_denominator = 0
        cross_group_hits = 0
        third_party_denominator = 0
        third_party_global_hits = 0
        bot_subject_denominator = 0
        bot_subject_hits = 0
        unknown_subject_denominator = 0
        unknown_subject_hits = 0
        extraction_latencies: list[float] = []
        retrieval_latencies: list[float] = []
        context_latencies: list[float] = []
        context_characters: list[float] = []
        extraction_requests = 0
        consolidation_requests = 0
        query_embedding_requests = 0
        eligible_extraction_events = 0
        eligible_claims = 0
        query_count = 0
        pipeline_errors = 0

        for result in results:
            case = by_id[result.case_id]
            observation = result.observation
            tags = set(case.tags)
            observed_claims = {
                claim_parts
                for item in observation.claims
                if (claim_parts := _claim_parts(item)) is not None
            }
            expected_claims = {
                claim_parts
                for item in case.expected_claims
                if (claim_parts := _claim_parts(item)) is not None
            }
            expected_claim_count += len(expected_claims)
            for expected in expected_claims:
                event_ref, scope, subject, memory_key, content = expected
                same_claim = {
                    item
                    for item in observed_claims
                    if item[0] == event_ref and item[3:] == (memory_key, content)
                }
                correct_subject_count += int(any(item[2] == subject for item in same_claim))
                correct_scope_count += int(any(item[1] == scope for item in same_claim))

            wanted_facts = {fact_key(item) for item in case.expected_facts}
            observed_facts = set(observation.facts)
            expected_fact_count += len(wanted_facts)
            exact_fact_count += len(wanted_facts & observed_facts)
            expected_by_ref = {
                item.fact_ref: item for item in (*case.initial_facts, *case.expected_facts)
            }
            generated_fact_refs = {item.fact_ref for item in case.expected_facts} - {
                item.fact_ref for item in case.initial_facts
            }
            evidence_fact_refs = {
                evidence_parts[0]
                for item in observation.evidence
                if (evidence_parts := _evidence_parts(item)) is not None
            }
            for observed in observed_facts:
                observed_parts = _fact_parts(observed)
                if len(observed_parts) < 10:
                    continue
                fact_ref, _scope, _subject, _group, _kind, _memory_key, _content, status = (
                    observed_parts[:8]
                )
                spec = expected_by_ref.get(fact_ref)
                if spec is not None:
                    expected_state_count += 1
                    correct_state_count += int(status == spec.status)
                    if fact_ref in generated_fact_refs and spec.source_type in {
                        "automatic",
                        "rebuild",
                    }:
                        observed_derived_fact_count += 1
                        fact_without_evidence_count += int(fact_ref not in evidence_fact_refs)
                if status == "active":
                    active_slot_count += 1
            slots = Counter(
                (
                    active_parts[1],
                    active_parts[2],
                    active_parts[3],
                    active_parts[4],
                    active_parts[5],
                )
                for item in observed_facts
                if len(active_parts := _fact_parts(item)) >= 8 and active_parts[7] == "active"
            )
            duplicate_active_fact_count += sum(max(0, count - 1) for count in slots.values())

            wanted_evidence = {evidence_key(item) for item in case.expected_evidence}
            expected_evidence_count += len(wanted_evidence)
            exact_evidence_count += len(wanted_evidence & set(observation.evidence))
            evidence_count += len(observation.evidence)
            duplicate_evidence_count += len(observation.evidence) - len(set(observation.evidence))
            events = {item.event_ref: item for item in case.events}
            outbound_event_count += sum(item.direction == "outbound" for item in case.events)
            bot_event_count += sum(item.speaker == "bot" for item in case.events)
            blank_event_count += sum(not item.content.strip() for item in case.events)
            for evidence in observation.evidence:
                observed_evidence_parts = _evidence_parts(evidence)
                if observed_evidence_parts is None:
                    source_event_mismatch_count += 1
                    continue
                _fact_ref, event_ref, speaker, _relation, excerpt = observed_evidence_parts
                event = events.get(event_ref)
                mismatch = (
                    event is None
                    or speaker != event.speaker
                    or not excerpt.strip()
                    or excerpt not in event.content
                )
                source_event_mismatch_count += int(mismatch)
                if event is not None:
                    outbound_evidence_count += int(event.direction == "outbound")
                    bot_evidence_count += int(event.speaker == "bot")
                    blank_evidence_count += int(not event.content.strip())

            if "cross_person" in tags:
                cross_person_denominator += max(
                    1, len(observation.facts) + len(observation.context)
                )
                cross_person_hits += self._forbidden_hits(case, result, group_only=False)
            if "cross_group" in tags:
                cross_group_denominator += max(1, len(observation.facts) + len(observation.context))
                cross_group_hits += self._forbidden_hits(case, result, group_only=True)
            if "third_party" in tags:
                third_party_denominator += max(1, len(observation.facts))
                third_party_global_hits += sum(
                    any(forbidden in item for item in observation.facts)
                    for forbidden in case.forbidden_facts
                )
                third_party_misattributions += int(not result.passed)
            if "bot" in tags:
                bot_subject_denominator += max(
                    1, sum(item.speaker == "bot" for item in case.events)
                )
                bot_subject_hits += len(observation.claims)
            if "unknown_subject" in tags:
                unknown_subject_denominator += 1
                unknown_subject_hits += len(observation.claims)

            for query in case.queries:
                expected_query_refs = set(query.expected_fact_refs)
                observed_query_refs = [
                    item.split("|", 1)[1]
                    for item in observation.retrieval
                    if item.startswith(f"{query.query_ref}|")
                ]
                expected_retrieval_count += len(expected_query_refs)
                retrieved_count += len(observed_query_refs)
                relevant_retrieved += len(expected_query_refs & set(observed_query_refs))
                wrong_target_retrieval += len(
                    set(observed_query_refs) & set(query.forbidden_fact_refs)
                )
                positions = [
                    index
                    for index, item in enumerate(observed_query_refs, start=1)
                    if item in expected_query_refs
                ]
                if expected_query_refs:
                    reciprocal_ranks.append(1 / min(positions) if positions else 0)
                    dcg = sum(1 / math.log2(index + 1) for index in positions)
                    ideal = sum(
                        1 / math.log2(index + 1)
                        for index in range(1, min(len(expected_query_refs), query.limit) + 1)
                    )
                    ndcgs.append(dcg / ideal if ideal else 0)
                if query.context:
                    observed_context = [
                        item.split("|", 1)[1]
                        for item in observation.context
                        if item.startswith(f"{query.query_ref}|")
                    ]
                    expected_context_count += len(expected_query_refs)
                    observed_context_count += len(observed_context)
                    relevant_context_count += len(expected_query_refs & set(observed_context))
                    forbidden_hits = len(set(observed_context) & set(query.forbidden_fact_refs))
                    wrong_subject_context += forbidden_hits
                    if "cross_group" in tags:
                        wrong_group_context += forbidden_hits
            contested_context_leaks += sum(
                1
                for failure in result.failures
                if "forbidden_context" in failure and "contested" in tags
            )

            if case.category == "correction":
                correction_cases += 1
                correction_passed += int(result.passed)
            if "retraction" in tags:
                retraction_cases += 1
                retraction_passed += int(result.passed)
            if case.category == "conflict":
                conflict_cases += 1
                conflict_passed += int(result.passed)
            if "historical" in tags:
                historical_cases += 1
                historical_failures += int(
                    observation.rebuild is None
                    or observation.rebuild.historical_regressions > 0
                    or not result.passed
                )
            if "idempotency" in tags:
                idempotency_cases += 1
                idempotency_failures += int(not result.passed)
            if case.category == "rebuild":
                rebuild_cases += 1
                rebuild_review_bypasses += int("review_bypass" in result.failures)
                rebuild_duplicate_commits += int("duplicate_commit" in result.failures)
                rebuild_historical_overwrites += int(
                    observation.rebuild is not None
                    and observation.rebuild.historical_regressions > 0
                )
                if case.expected_rebuild is not None:
                    rebuild_receipt_cases += 1
                    rebuild_receipt_correct += int(
                        observation.rebuild is not None
                        and observation.rebuild.receipts == case.expected_rebuild.receipts
                    )
                if "resume" in tags:
                    rebuild_resume_cases += 1
                    rebuild_resume_correct += int(result.passed)

            extraction_latencies.append(observation.extraction_latency_ms)
            retrieval_latencies.extend(observation.retrieval_latency_ms)
            context_latencies.extend(observation.context_latency_ms)
            context_characters.append(float(observation.context_characters))
            extraction_requests += observation.extraction_requests
            consolidation_requests += observation.consolidation_requests
            query_embedding_requests += observation.query_embedding_requests
            eligible_extraction_events += sum(
                item.direction == "inbound" and item.speaker != "bot" and bool(item.content.strip())
                for item in case.events
            )
            eligible_claims += len(case.expected_claims)
            query_count += len(case.queries)
            pipeline_errors += int(observation.error_code is not None)

        total_cases = len(results)
        metrics = {
            "case_pass_rate": ratio(sum(item.passed for item in results), total_cases),
            "subject_attribution_accuracy": ratio(correct_subject_count, expected_claim_count),
            "scope_attribution_accuracy": ratio(correct_scope_count, expected_claim_count),
            "cross_person_contamination_rate": ratio(cross_person_hits, cross_person_denominator),
            "cross_group_contamination_rate": ratio(cross_group_hits, cross_group_denominator),
            "third_party_global_leak_rate": ratio(third_party_global_hits, third_party_denominator),
            "bot_subject_rate": ratio(bot_subject_hits, bot_subject_denominator),
            "unknown_subject_acceptance_rate": ratio(
                unknown_subject_hits, unknown_subject_denominator
            ),
            "fact_accuracy": ratio(exact_fact_count, expected_fact_count),
            "evidence_provenance_accuracy": ratio(exact_evidence_count, expected_evidence_count),
            "fact_without_evidence_rate": ratio(
                fact_without_evidence_count, observed_derived_fact_count
            ),
            "duplicate_evidence_rate": ratio(duplicate_evidence_count, evidence_count),
            "source_event_mismatch_rate": ratio(source_event_mismatch_count, evidence_count),
            "outbound_evidence_rate": ratio(outbound_evidence_count, outbound_event_count),
            "bot_evidence_rate": ratio(bot_evidence_count, bot_event_count),
            "blank_evidence_rate": ratio(blank_evidence_count, blank_event_count),
            "fact_state_accuracy": ratio(correct_state_count, expected_state_count),
            "correction_resolution_accuracy": ratio(correction_passed, correction_cases),
            "retraction_resolution_accuracy": ratio(retraction_passed, retraction_cases),
            "conflict_resolution_accuracy": ratio(conflict_passed, conflict_cases),
            "conflict_coactivation_rate": ratio(conflict_cases - conflict_passed, conflict_cases),
            "duplicate_active_fact_rate": ratio(duplicate_active_fact_count, active_slot_count),
            "historical_regression_rate": ratio(historical_failures, historical_cases),
            "idempotency_failure_rate": ratio(idempotency_failures, idempotency_cases),
            "precision_at_k": ratio(relevant_retrieved, retrieved_count),
            "recall_at_k": ratio(relevant_retrieved, expected_retrieval_count),
            "mean_reciprocal_rank": value(
                statistics.fmean(reciprocal_ranks) if reciprocal_ranks else None,
                unit="ratio",
            ),
            "ndcg_at_k": value(
                statistics.fmean(ndcgs) if ndcgs else None,
                unit="ratio",
            ),
            "wrong_target_retrieval_rate": ratio(wrong_target_retrieval, retrieved_count),
            "empty_query_fact_leak_rate": ratio(
                sum(
                    len(result.observation.retrieval)
                    for result in results
                    if "empty_query" in by_id[result.case_id].tags
                ),
                sum("empty_query" in item.tags for item in cases),
            ),
            "context_precision": ratio(relevant_context_count, observed_context_count),
            "context_recall": ratio(relevant_context_count, expected_context_count),
            "wrong_subject_context_rate": ratio(wrong_subject_context, observed_context_count),
            "wrong_group_context_rate": ratio(wrong_group_context, observed_context_count),
            "contested_context_leak_rate": ratio(
                contested_context_leaks,
                sum("contested" in item.tags for item in cases),
            ),
            "third_party_misattribution_rate": ratio(
                third_party_misattributions, third_party_denominator
            ),
            "rebuild_review_bypass_rate": ratio(rebuild_review_bypasses, rebuild_cases),
            "rebuild_duplicate_commit_rate": ratio(rebuild_duplicate_commits, rebuild_cases),
            "rebuild_historical_overwrite_rate": ratio(
                rebuild_historical_overwrites, historical_cases
            ),
            "rebuild_receipt_accuracy": ratio(rebuild_receipt_correct, rebuild_receipt_cases),
            "rebuild_resume_accuracy": ratio(rebuild_resume_correct, rebuild_resume_cases),
            "pipeline_error_rate": ratio(pipeline_errors, total_cases),
            "average_extraction_requests_per_event": ratio(
                extraction_requests, eligible_extraction_events, unit="requests"
            ),
            "average_consolidation_requests_per_claim": ratio(
                consolidation_requests, eligible_claims, unit="requests"
            ),
            "average_query_embedding_requests_per_query": ratio(
                query_embedding_requests, query_count, unit="requests"
            ),
            "average_context_characters": value(
                statistics.fmean(context_characters) if context_characters else None,
                unit="characters",
            ),
            "extraction_latency_p50_ms": value(
                percentile(extraction_latencies, 0.50), unit="milliseconds"
            ),
            "extraction_latency_p95_ms": value(
                percentile(extraction_latencies, 0.95), unit="milliseconds"
            ),
            "retrieval_latency_p50_ms": value(
                percentile(retrieval_latencies, 0.50), unit="milliseconds"
            ),
            "retrieval_latency_p95_ms": value(
                percentile(retrieval_latencies, 0.95), unit="milliseconds"
            ),
            "context_latency_p50_ms": value(
                percentile(context_latencies, 0.50), unit="milliseconds"
            ),
            "context_latency_p95_ms": value(
                percentile(context_latencies, 0.95), unit="milliseconds"
            ),
            "quality_suite_total_ms": value(sum(extraction_latencies), unit="milliseconds"),
            "total_model_requests": value(
                float(extraction_requests + consolidation_requests), unit="requests"
            ),
            "total_query_embedding_requests": value(
                float(query_embedding_requests), unit="requests"
            ),
        }
        return metrics

    @staticmethod
    def _forbidden_hits(
        case: MemoryQualityCase,
        result: QualityCaseResult,
        *,
        group_only: bool,
    ) -> int:
        fact_hits = sum(
            any(forbidden in item for item in result.observation.facts)
            for forbidden in case.forbidden_facts
        )
        context_hits = sum(
            any(forbidden in item for item in result.observation.context)
            for forbidden in case.forbidden_context
        )
        query_hits = sum(
            f"{query.query_ref}|{forbidden}" in result.observation.retrieval
            for query in case.queries
            for forbidden in query.forbidden_fact_refs
        )
        _ = group_only
        return fact_hits + context_hits + query_hits

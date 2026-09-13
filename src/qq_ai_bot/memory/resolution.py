"""Deterministic backend policy for Memory V2 claim resolution."""

from __future__ import annotations

from qq_ai_bot.memory.enums import (
    MemoryClaimOperation,
    MemoryConflictState,
    MemoryFactRelationType,
    MemoryResolutionAction,
    MemoryScopeType,
    MemorySemanticRelation,
    MemoryStatus,
)
from qq_ai_bot.memory.evidence import MemoryEvidencePolicy
from qq_ai_bot.memory.models import (
    CandidateRelation,
    MemoryCandidate,
    MemoryResolutionPlan,
)
from qq_ai_bot.memory.validation import ValidatedMemoryClaim


class MemoryResolutionPolicy:
    """Translate semantic suggestions into a validated persistence plan."""

    def __init__(self, evidence_policy: MemoryEvidencePolicy | None = None) -> None:
        self._evidence = evidence_policy or MemoryEvidencePolicy()

    def resolve(
        self,
        claim: ValidatedMemoryClaim,
        candidates: tuple[MemoryCandidate, ...],
        relations: tuple[CandidateRelation, ...] = (),
    ) -> MemoryResolutionPlan:
        identical = next(
            (
                candidate
                for candidate in candidates
                if candidate.fact.kind is claim.fact.kind and candidate.exact_content
            ),
            None,
        )
        if identical is not None and claim.operation is not MemoryClaimOperation.RETRACT:
            return self._plan(
                MemoryResolutionAction.MERGE_EVIDENCE,
                existing=identical.fact.id,
                reason="identical_claim",
            )

        exact = tuple(candidate for candidate in candidates if candidate.exact_key)
        subject_controls_target = claim.subject_is_speaker or claim.fact.scope_type in {
            MemoryScopeType.GROUP,
            MemoryScopeType.SELF,
        }
        if claim.operation is MemoryClaimOperation.RETRACT:
            if len(exact) == 1 and subject_controls_target:
                return self._plan(
                    MemoryResolutionAction.INVALIDATE,
                    existing=exact[0].fact.id,
                    reason="user_retracted",
                )
            return self._plan(MemoryResolutionAction.NOOP, reason="retract_target_ambiguous")
        if claim.operation is MemoryClaimOperation.CORRECT and len(exact) == 1:
            if subject_controls_target:
                return self._plan(
                    MemoryResolutionAction.SUPERSEDE,
                    existing=exact[0].fact.id,
                    reason="explicit_correction",
                    create=True,
                )
            return self._contest(exact[0].fact.id, "third_party_correction_contested")
        if not candidates:
            return self._plan(
                MemoryResolutionAction.CREATE,
                reason="no_candidate",
                create=True,
            )

        by_ref = {candidate.candidate_ref: candidate for candidate in candidates}
        suggested = max(relations, key=lambda item: item.confidence, default=None)
        candidate = by_ref.get(suggested.candidate_ref) if suggested is not None else None
        if suggested is None or candidate is None:
            if len(exact) == 1:
                return self._contest(exact[0].fact.id, "classifier_unavailable")
            return self._plan(
                MemoryResolutionAction.CREATE,
                reason="classifier_unavailable_no_exact_key",
                create=True,
            )
        if suggested.relation in {
            MemorySemanticRelation.SAME_CLAIM,
            MemorySemanticRelation.CONFIRMS,
        }:
            return self._plan(
                MemoryResolutionAction.MERGE_EVIDENCE,
                existing=candidate.fact.id,
                reason=suggested.relation.value,
            )
        if suggested.relation is MemorySemanticRelation.RETRACTS:
            if subject_controls_target:
                return self._plan(
                    MemoryResolutionAction.INVALIDATE,
                    existing=candidate.fact.id,
                    reason="user_retracted",
                )
            return self._plan(MemoryResolutionAction.NOOP, reason="retraction_denied")
        if suggested.relation is MemorySemanticRelation.SUPERSEDES:
            if subject_controls_target or self._stronger(claim, candidate):
                return self._plan(
                    MemoryResolutionAction.SUPERSEDE,
                    existing=candidate.fact.id,
                    reason="semantic_successor",
                    create=True,
                )
            return self._contest(candidate.fact.id, "lower_authority_successor")
        if suggested.relation is MemorySemanticRelation.CONTRADICTS:
            if self._stronger(claim, candidate):
                return self._plan(
                    MemoryResolutionAction.SUPERSEDE,
                    existing=candidate.fact.id,
                    reason="higher_authority_contradiction",
                    create=True,
                    relations=(MemoryFactRelationType.CONTRADICTS,),
                )
            return self._contest(candidate.fact.id, "unresolved_contradiction")
        if suggested.relation in {
            MemorySemanticRelation.COEXISTS,
            MemorySemanticRelation.UNRELATED,
        }:
            if any(item.exact_key for item in candidates):
                return self._contest(candidate.fact.id, "coexisting_key_collision")
            return self._plan(
                MemoryResolutionAction.CREATE,
                reason=suggested.relation.value,
                create=True,
            )
        return self._plan(MemoryResolutionAction.NOOP, reason="unsupported_relation")

    def _stronger(self, claim: ValidatedMemoryClaim, candidate: MemoryCandidate) -> bool:
        return self._evidence.authority_rank(claim.fact.authority) > self._evidence.authority_rank(
            candidate.fact.authority
        )

    @staticmethod
    def _contest(existing: int, reason: str) -> MemoryResolutionPlan:
        return MemoryResolutionPlan(
            action=MemoryResolutionAction.CONTEST,
            existing_fact_id=existing,
            new_fact_status=MemoryStatus.CONTESTED,
            new_conflict_state=MemoryConflictState.CONTESTED,
            existing_status=MemoryStatus.ACTIVE,
            existing_conflict_state=MemoryConflictState.CONTESTED,
            relation_types=(MemoryFactRelationType.CONTRADICTS,),
            reason_code=reason,
            append_evidence=True,
            create_new_fact=True,
        )

    @staticmethod
    def _plan(
        action: MemoryResolutionAction,
        *,
        reason: str,
        existing: int | None = None,
        create: bool = False,
        relations: tuple[MemoryFactRelationType, ...] = (),
    ) -> MemoryResolutionPlan:
        return MemoryResolutionPlan(
            action=action,
            existing_fact_id=existing,
            reason_code=reason,
            relation_types=relations,
            append_evidence=action is not MemoryResolutionAction.NOOP,
            create_new_fact=create,
        )

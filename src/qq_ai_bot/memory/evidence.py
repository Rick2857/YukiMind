"""Central authority and evidence-confidence policy for Memory V2."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from qq_ai_bot.memory.enums import MemoryAuthority, MemoryEvidenceRelation
from qq_ai_bot.memory.models import MemoryEvidence, MemoryEvidenceCreate


@dataclass(frozen=True, slots=True)
class MemoryEvidenceWeights:
    explicit: float = 1.0
    self_report: float = 0.9
    group_report: float = 0.7
    third_party: float = 0.55
    rebuild: float = 0.75
    cap_explicit: float = 1.0
    cap_self: float = 0.98
    cap_group: float = 0.9
    cap_third_party: float = 0.75


class MemoryEvidencePolicy:
    """Compute confidence and authority without model judgment."""

    _AUTHORITY_RANK: ClassVar[dict[MemoryAuthority, int]] = {
        MemoryAuthority.THIRD_PARTY: 0,
        MemoryAuthority.GROUP_REPORT: 1,
        MemoryAuthority.SELF_REPORT: 2,
        MemoryAuthority.AGENT_REFLECTION: 3,
        MemoryAuthority.EXPLICIT: 4,
    }

    def __init__(self, weights: MemoryEvidenceWeights | None = None) -> None:
        self.weights = weights or MemoryEvidenceWeights()

    def strongest_authority(
        self,
        authorities: Iterable[MemoryAuthority],
        *,
        default: MemoryAuthority,
    ) -> MemoryAuthority:
        return max(authorities, key=self.authority_rank, default=default)

    def authority_rank(self, authority: MemoryAuthority) -> int:
        return self._AUTHORITY_RANK[authority]

    def aggregate(
        self,
        evidence: Iterable[MemoryEvidence | MemoryEvidenceCreate],
        *,
        authority: MemoryAuthority,
    ) -> float:
        weights = tuple(self._positive_weight(row) for row in evidence)
        positive = tuple(value for value in weights if value > 0)
        combined = 0.0 if not positive else 1.0 - math.prod(1.0 - value for value in positive)
        return min(self.authority_cap(authority), max(0.0, combined))

    def authority_cap(self, authority: MemoryAuthority) -> float:
        return {
            MemoryAuthority.EXPLICIT: self.weights.cap_explicit,
            MemoryAuthority.SELF_REPORT: self.weights.cap_self,
            MemoryAuthority.AGENT_REFLECTION: self.weights.cap_self,
            MemoryAuthority.GROUP_REPORT: self.weights.cap_group,
            MemoryAuthority.THIRD_PARTY: self.weights.cap_third_party,
        }[authority]

    def _positive_weight(self, evidence: MemoryEvidence | MemoryEvidenceCreate) -> float:
        if evidence.relation is MemoryEvidenceRelation.RETRACTION:
            return 0.0
        base = {
            MemoryEvidenceRelation.EXPLICIT_COMMAND: self.weights.explicit,
            MemoryEvidenceRelation.CORRECTION: self.weights.explicit,
            MemoryEvidenceRelation.SELF_STATEMENT: self.weights.self_report,
            MemoryEvidenceRelation.CONFIRMATION: self.weights.self_report,
            MemoryEvidenceRelation.GROUP_STATEMENT: self.weights.group_report,
            MemoryEvidenceRelation.THIRD_PARTY_STATEMENT: self.weights.third_party,
            MemoryEvidenceRelation.REBUILD: self.weights.rebuild,
            MemoryEvidenceRelation.AGENT_REFLECTION: self.weights.self_report,
        }[evidence.relation]
        return min(1.0, max(0.0, base * evidence.confidence))

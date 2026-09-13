"""Deterministic lifecycle policy for current Memory V2 facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from qq_ai_bot.memory.enums import (
    MemoryAuthority,
    MemoryInvalidationReason,
    MemorySourceType,
    MemoryStatus,
)
from qq_ai_bot.memory.models import MemoryFact


@dataclass(frozen=True, slots=True)
class MemoryLifecycleConfig:
    automatic_stale_days: int
    third_party_stale_days: int
    contested_stale_days: int
    stale_max_importance: int
    stale_max_confidence: float


class MemoryLifecyclePolicy:
    def reason(
        self,
        fact: MemoryFact,
        *,
        now: datetime,
        config: MemoryLifecycleConfig,
    ) -> MemoryInvalidationReason | None:
        if fact.valid_until is not None and fact.valid_until <= now:
            return MemoryInvalidationReason.EXPIRED
        if (
            fact.source_type is MemorySourceType.EXPLICIT
            or fact.authority is MemoryAuthority.EXPLICIT
        ):
            return None
        if fact.source_type is not MemorySourceType.AUTOMATIC:
            return None
        if fact.importance > config.stale_max_importance:
            return None
        if fact.confidence > config.stale_max_confidence:
            return None
        days = (
            config.third_party_stale_days
            if fact.authority is MemoryAuthority.THIRD_PARTY
            else config.contested_stale_days
            if fact.status is MemoryStatus.CONTESTED
            else config.automatic_stale_days
        )
        return (
            MemoryInvalidationReason.STALE
            if fact.last_confirmed_at <= now - timedelta(days=days)
            else None
        )

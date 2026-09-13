"""Stable task contracts for bounded background memory reflection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MemoryReflectionIssue(StrEnum):
    DUPLICATE = "duplicate"
    CONTESTED = "contested"
    ATTRIBUTION = "attribution"


@dataclass(frozen=True, slots=True)
class MemoryReflectionCandidate:
    issue_type: MemoryReflectionIssue
    fact_id: int
    related_fact_id: int | None = None


@dataclass(frozen=True, slots=True)
class MemoryReflectionJob:
    id: int
    fingerprint: str
    issue_type: MemoryReflectionIssue
    fact_id: int
    related_fact_id: int | None
    status: str
    attempts: int
    max_attempts: int
    next_attempt_at: datetime
    claimed_at: datetime | None
    error_category: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

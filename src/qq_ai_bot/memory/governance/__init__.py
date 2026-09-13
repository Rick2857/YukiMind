"""Deterministic governance of duplicate, contested, and misattributed facts.

The legacy ``memory_reflection_jobs`` table name remains unchanged for migration
compatibility; this package supplies the accurate code-level name.
"""

from qq_ai_bot.memory.reflection.models import (
    MemoryReflectionCandidate as MemoryGovernanceCandidate,
)
from qq_ai_bot.memory.reflection.models import MemoryReflectionIssue as MemoryGovernanceIssue
from qq_ai_bot.memory.reflection.models import MemoryReflectionJob as MemoryGovernanceJob
from qq_ai_bot.memory.reflection.repository import (
    MemoryReflectionRepository as MemoryGovernanceRepository,
)
from qq_ai_bot.memory.reflection.worker import MemoryReflectionWorker as MemoryGovernanceWorker

__all__ = [
    "MemoryGovernanceCandidate",
    "MemoryGovernanceIssue",
    "MemoryGovernanceJob",
    "MemoryGovernanceRepository",
    "MemoryGovernanceWorker",
]

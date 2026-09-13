"""Qwen-backed, rebuildable Memory V2 embedding infrastructure."""

from qq_ai_bot.memory.embedding.codec import Float32VectorCodec
from qq_ai_bot.memory.embedding.fake import FakeEmbeddingProvider
from qq_ai_bot.memory.embedding.models import (
    EmbeddingBatchResult,
    EmbeddingProviderCapabilities,
    EmbeddingProviderProfile,
    EmbeddingUsage,
    EmbeddingVector,
    MemoryEmbeddingHealth,
    MemoryEmbeddingJob,
    MemoryEmbeddingJobStatus,
    MemoryEmbeddingProfileRecord,
    MemoryEmbeddingRecord,
    MemorySemanticCandidate,
)
from qq_ai_bot.memory.embedding.provider import EmbeddingProvider, EmbeddingProviderError
from qq_ai_bot.memory.embedding.qwen import QwenDashScopeEmbeddingProvider
from qq_ai_bot.memory.embedding.text import EmbeddingDocumentBuilder, EmbeddingQueryBuilder

__all__ = [
    "EmbeddingBatchResult",
    "EmbeddingDocumentBuilder",
    "EmbeddingProvider",
    "EmbeddingProviderCapabilities",
    "EmbeddingProviderError",
    "EmbeddingProviderProfile",
    "EmbeddingQueryBuilder",
    "EmbeddingUsage",
    "EmbeddingVector",
    "FakeEmbeddingProvider",
    "Float32VectorCodec",
    "MemoryEmbeddingHealth",
    "MemoryEmbeddingJob",
    "MemoryEmbeddingJobStatus",
    "MemoryEmbeddingProfileRecord",
    "MemoryEmbeddingRecord",
    "MemorySemanticCandidate",
    "QwenDashScopeEmbeddingProvider",
]

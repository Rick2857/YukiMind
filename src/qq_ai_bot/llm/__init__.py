"""LLM provider implementations."""

from qq_ai_bot.domain.messages import ProviderContinuation
from qq_ai_bot.llm.base import (
    LLMAuthenticationError,
    LLMEmptyResponseError,
    LLMError,
    LLMIncompleteResponseError,
    LLMInvalidRequestError,
    LLMInvalidResponseError,
    LLMNativeToolError,
    LLMProvider,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    LLMUnsupportedFeatureError,
)
from qq_ai_bot.llm.fake import FakeLLMProvider
from qq_ai_bot.llm.openai_compatible import OpenAICompatibleProvider

__all__ = [
    "FakeLLMProvider",
    "LLMAuthenticationError",
    "LLMEmptyResponseError",
    "LLMError",
    "LLMIncompleteResponseError",
    "LLMInvalidRequestError",
    "LLMInvalidResponseError",
    "LLMNativeToolError",
    "LLMProvider",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMUnavailableError",
    "LLMUnsupportedFeatureError",
    "OpenAICompatibleProvider",
    "ProviderContinuation",
]

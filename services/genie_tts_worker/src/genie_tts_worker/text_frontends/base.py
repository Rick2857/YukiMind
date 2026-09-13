"""Provider-neutral contracts for deterministic speech-only text transforms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class SpeechTextFrontendUnavailable(RuntimeError):
    """A configured local frontend cannot safely process its language."""


@dataclass(frozen=True, slots=True)
class ProcessedSpeechText:
    original_text_hash: str
    spoken_text: str
    spoken_text_hash: str
    language: str
    frontend_version: str
    transformed_tokens: tuple[str, ...]


class SpeechTextFrontend(Protocol):
    @property
    def language(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def signature(self) -> str: ...

    def process(self, text: str) -> ProcessedSpeechText: ...

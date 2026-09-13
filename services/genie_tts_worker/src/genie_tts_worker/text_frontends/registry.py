"""Language keyed speech frontend registry and health state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from genie_tts_worker.text_frontends.base import (
    ProcessedSpeechText,
    SpeechTextFrontend,
    SpeechTextFrontendUnavailable,
)
from genie_tts_worker.text_frontends.japanese import JapaneseSpeechFrontend


@dataclass(frozen=True, slots=True)
class SpeechFrontendHealth:
    language: str
    enabled: bool
    available: bool
    version: str | None = None
    signature: str | None = None
    detail: str = ""


class SpeechFrontendRegistry:
    def __init__(
        self,
        frontends: tuple[SpeechTextFrontend, ...] = (),
        health: tuple[SpeechFrontendHealth, ...] = (),
    ) -> None:
        self._frontends = {frontend.language: frontend for frontend in frontends}
        self._health = {item.language: item for item in health}

    @classmethod
    def build_japanese(
        cls,
        *,
        enabled: bool,
        asset_dir: Path,
        lexicon_path: Path,
    ) -> SpeechFrontendRegistry:
        if not enabled:
            return cls(health=(SpeechFrontendHealth("jp", False, False),))
        try:
            frontend = JapaneseSpeechFrontend(asset_dir=asset_dir, lexicon_path=lexicon_path)
        except SpeechTextFrontendUnavailable as exc:
            return cls(health=(SpeechFrontendHealth("jp", True, False, detail=str(exc)),))
        return cls(
            frontends=(frontend,),
            health=(
                SpeechFrontendHealth(
                    "jp",
                    True,
                    True,
                    frontend.version,
                    frontend.signature,
                ),
            ),
        )

    def process(self, language: str, text: str) -> ProcessedSpeechText | None:
        normalized = _normalize_language(language)
        frontend = self._frontends.get(normalized)
        status = self._health.get(normalized)
        if frontend is not None:
            return frontend.process(text)
        if status is not None and status.enabled and not status.available:
            raise SpeechTextFrontendUnavailable(status.detail)
        return None

    def health(self, language: str) -> SpeechFrontendHealth | None:
        return self._health.get(_normalize_language(language))


def _normalize_language(language: str) -> str:
    return "jp" if language.casefold() in {"ja", "jp", "japanese"} else language.casefold()

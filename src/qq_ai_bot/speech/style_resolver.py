"""Deterministic, LLM-free reference style selection."""

from __future__ import annotations

import unicodedata

from qq_ai_bot.speech.models import VoiceProfile, VoiceReference


class StyleResolver:
    def resolve(self, profile: VoiceProfile, style_hint: str) -> VoiceReference:
        enabled = tuple(item for item in profile.references if item.enabled)
        if not enabled:
            raise LookupError("voice profile has no enabled references")
        hint = style_hint.strip().casefold()
        normalized_hint = self._normalize(hint)
        ordered = sorted(enabled, key=lambda item: (-item.priority, item.reference_key))
        if hint:
            for item in ordered:
                if item.style.casefold() == hint:
                    return item
            for item in ordered:
                if hint in {alias.casefold() for alias in item.aliases}:
                    return item
            for item in ordered:
                candidates = (item.style, *item.aliases)
                if normalized_hint and normalized_hint in {
                    self._normalize(candidate) for candidate in candidates
                }:
                    return item
        defaults = [item for item in ordered if item.style == profile.default_style]
        if len(defaults) != 1:
            raise LookupError("voice profile default reference is unavailable")
        return defaults[0]

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(
            character.casefold()
            for character in unicodedata.normalize("NFKC", value)
            if character.isalnum()
        )

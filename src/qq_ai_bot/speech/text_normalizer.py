"""Convert display-oriented Markdown into text suitable for local speech."""

from __future__ import annotations

import re
import unicodedata

NORMALIZER_VERSION = "speech-text-v1"

_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_MARKERS = re.compile(r"\[(?:tool|source|来源|工具)[^\]]*\]", re.IGNORECASE)
_MARKDOWN = re.compile(r"(?:^|(?<=\s))[#>*_~-]+|[*_~]{1,3}")
_SPACE = re.compile(r"[ \t\f\v]+")
_LINES = re.compile(r"\s*\n+\s*")


def normalize_speech_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = _FENCE.sub(" ", normalized)
    normalized = _INLINE_CODE.sub(r"\1", normalized)
    normalized = _LINK.sub(r"\1", normalized)
    normalized = _URL.sub("链接", normalized)
    normalized = _MARKERS.sub(" ", normalized)
    normalized = _MARKDOWN.sub("", normalized)
    normalized = _LINES.sub("，", normalized)
    normalized = _SPACE.sub(" ", normalized)
    return normalized.strip(" ，")

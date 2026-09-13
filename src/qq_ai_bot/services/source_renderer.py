"""Render persisted sources and remove model-controlled source material."""

from __future__ import annotations

import re

from qq_ai_bot.web.base import WebSearchError, normalize_public_url
from qq_ai_bot.web.models import WebSearchSource

_SOURCE_SECTION = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?"
    r"(?:来源|出处|参考资料|引用|sources?|references?|citations?)"
    r"[ \t]*[:：]?[ \t]*$"
)
_INLINE_SOURCE_SECTION = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?"
    r"(?:来源|出处|参考资料|sources?|references?|citations?)"
    r"[ \t]*[:：][ \t]*(?:\d+[.)、]|[-*+]|\[?\d+]|https?://)"
)
_NUMERIC_CITATION = re.compile(r"\[\d{1,2}]")


class SourceRenderer:
    """Keep URLs backend-owned and render only actual persisted sources."""

    def sanitize_model_text(
        self,
        text: str,
        sources: tuple[WebSearchSource, ...],
    ) -> str:
        """Remove trailing source blocks, citation markers, and used-source URLs."""

        cleaned = text
        matches = list(_SOURCE_SECTION.finditer(cleaned))
        inline_matches = list(_INLINE_SOURCE_SECTION.finditer(cleaned))
        candidates = [*matches, *inline_matches]
        if candidates:
            marker = min(candidates, key=lambda item: item.start())
            cleaned = cleaned[: marker.start()].rstrip()
        for source in self._deduplicate(sources, maximum=max(1, len(sources))):
            variants = {source.url}
            try:
                normalized = normalize_public_url(source.url)
                variants.add(normalized)
                if normalized.endswith("/"):
                    variants.add(normalized[:-1])
            except WebSearchError:
                pass
            for url in sorted((item for item in variants if item), key=len, reverse=True):
                cleaned = re.sub(
                    rf"\[([^\]]+)]\(\s*{re.escape(url)}\s*\)",
                    r"\1",
                    cleaned,
                    flags=re.IGNORECASE,
                )
                cleaned = re.sub(re.escape(url), "", cleaned, flags=re.IGNORECASE)
        if sources:
            cleaned = _NUMERIC_CITATION.sub("", cleaned)
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def render(
        self,
        sources: tuple[WebSearchSource, ...],
        *,
        maximum: int = 5,
    ) -> str:
        """Render a bounded number of real sources as one independent QQ message."""

        unique = self._deduplicate(sources, maximum=max(1, min(maximum, 20)))
        if not unique:
            return ""
        lines = ["来源："]
        for index, source in enumerate(unique, start=1):
            title = " ".join(source.title.split()) or source.domain or "未命名页面"
            lines.extend((f"{index}. {title}", f"   {source.url}"))
        return "\n".join(lines)

    @staticmethod
    def _deduplicate(
        sources: tuple[WebSearchSource, ...],
        *,
        maximum: int,
    ) -> tuple[WebSearchSource, ...]:
        seen: set[str] = set()
        unique: list[WebSearchSource] = []
        for source in sources:
            try:
                key = normalize_public_url(source.url)
            except WebSearchError:
                continue
            if key in seen:
                continue
            seen.add(key)
            unique.append(source)
            if len(unique) >= maximum:
                break
        return tuple(unique)

"""Backend-owned source display intent classification."""

from __future__ import annotations

import re

_NEGATION = re.compile(
    r"(?:不要|不用|无需|别|不必|不需要).{0,8}(?:来源|出处|链接|网址|引用|参考资料|证据)"
    r"|(?:no|without|do\s+not\s+(?:show|include|provide)).{0,12}"
    r"(?:sources?|citations?|references?|links?)",
    re.IGNORECASE,
)
_META_LANGUAGE = re.compile(
    r"(?:来源|出处|引用|citation|source).{0,8}(?:这个词|词语|是什么意思|含义|翻译|怎么说)",
    re.IGNORECASE,
)
_SOURCE_NOUN = re.compile(
    r"(?:来源|出处|原文链接|参考资料|引用|网址|链接|证据|"
    r"sources?|citations?|references?(?:\s+links?)?)",
    re.IGNORECASE,
)
_REQUEST_SIGNAL = re.compile(
    r"(?:给出|给我|附上|提供|发我|发来|告诉|列出|显示|注明|标注|是什么|有哪些|"
    r"从哪(?:里|儿)?|哪(?:里|儿).*(?:查|来)|有.{0,4}吗|"
    r"please|show|give|provide|include|list|cite|where|send)",
    re.IGNORECASE,
)
_ENGLISH_DIRECT = re.compile(
    r"^\s*(?:sources?|citations?|references?(?:\s+links?)?)\s*[?？!！.。]?\s*$",
    re.IGNORECASE,
)
_STANDALONE_PATTERNS = (
    re.compile(
        r"^\s*(?:来源|来源呢|出处|出处呢|链接|链接呢|网址|网址呢|参考资料|引用)"
        r"\s*[?？!！.。]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:请|麻烦)?(?:把)?(?:来源|出处|链接|网址|参考资料)"
        r"(?:发|给|发给)(?:我|一下)?\s*[?？!！.。]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*从哪(?:里|儿)?查(?:(?:到|来)的|的)?\s*[?？!！.。]?\s*$"),
    _ENGLISH_DIRECT,
    re.compile(
        r"^\s*(?:show|give|send|provide)\s+(?:me\s+)?"
        r"(?:the\s+)?(?:sources?|citations?|references?|links?)\s*[?!.]?\s*$",
        re.IGNORECASE,
    ),
)


class SourceDisplayPolicy:
    """Determine source intent without delegating display authority to the LLM."""

    def requested(self, text: str) -> bool:
        """Return whether this user message explicitly asks to see sources."""

        normalized = " ".join(text.split())
        if not normalized or _NEGATION.search(normalized) or _META_LANGUAGE.search(normalized):
            return False
        if self.standalone_request(normalized):
            return True
        if _ENGLISH_DIRECT.fullmatch(normalized):
            return True
        noun = _SOURCE_NOUN.search(normalized)
        return noun is not None and _REQUEST_SIGNAL.search(normalized) is not None

    def standalone_request(self, text: str) -> bool:
        """Recognize a short follow-up that only asks for the prior sources."""

        normalized = " ".join(text.split())
        if (
            not normalized
            or len(normalized) > 40
            or _NEGATION.search(normalized)
            or _META_LANGUAGE.search(normalized)
        ):
            return False
        return any(pattern.fullmatch(normalized) is not None for pattern in _STANDALONE_PATTERNS)

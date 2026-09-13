"""Test-only provider doubles shared across suites."""

from __future__ import annotations

from dataclasses import replace

from qq_ai_bot.web.base import WebSearchError, normalize_public_url
from qq_ai_bot.web.models import WebSearchRequest, WebSearchResponse, WebSearchSource


class FakeWebSearchProvider:
    """Return configured web responses without performing network access."""

    def __init__(
        self,
        *,
        response: WebSearchResponse | None = None,
        extracted: dict[str, WebSearchSource] | None = None,
        error: WebSearchError | None = None,
    ) -> None:
        self.response = response
        self.extracted = {
            normalize_public_url(url): source for url, source in (extracted or {}).items()
        }
        self.error = error
        self.search_requests: list[WebSearchRequest] = []
        self.extract_requests: list[tuple[str, str]] = []
        self.closed = False

    async def search(self, request: WebSearchRequest) -> WebSearchResponse:
        self.search_requests.append(request)
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise WebSearchError("empty_results", "没有找到可用的联网结果")
        return replace(self.response, query=request.query)

    async def extract(self, url: str, query: str) -> WebSearchSource:
        normalized = normalize_public_url(url)
        self.extract_requests.append((normalized, query))
        if self.error is not None:
            raise self.error
        source = self.extracted.get(normalized)
        if source is None:
            raise WebSearchError("extract_failed", "网页正文提取失败")
        return source

    async def close(self) -> None:
        self.closed = True

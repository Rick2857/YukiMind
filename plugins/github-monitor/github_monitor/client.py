"""Read-only GitHub REST client over the Host HTTP facade."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from yuki_plugin_sdk.context import PluginContext

from .errors import GitHubAPIError
from .models import GitHubAPIResponse, RateLimitState


class GitHubClient:
    def __init__(self, context: PluginContext, *, version: str = "1.0.0") -> None:
        self._context = context
        self._headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"Yuki-GitHub-Monitor/{version}",
        }

    async def repository_events(
        self,
        repository: str,
        *,
        per_page: int,
        etag: str = "",
        last_modified: str = "",
        page: int = 1,
    ) -> GitHubAPIResponse:
        headers = dict(self._headers)
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        path = quote(repository, safe="/")
        return await self._get(
            f"https://api.github.com/repos/{path}/events?per_page={per_page}&page={page}",
            headers=headers,
        )

    async def compare(self, repository: str, before: str, head: str) -> GitHubAPIResponse:
        path = quote(repository, safe="/")
        span = f"{quote(before, safe='')}...{quote(head, safe='')}"
        return await self._get(
            f"https://api.github.com/repos/{path}/compare/{span}",
            headers=self._headers,
        )

    async def _get(self, url: str, *, headers: dict[str, str]) -> GitHubAPIResponse:
        result = await self._context.http.request(
            "GET",
            url,
            headers=headers,
            auth_secret=(
                "GITHUB_TOKEN" if self._context.secrets.configured("GITHUB_TOKEN") else None
            ),
        )
        data = result.data
        status = int(data.get("status_code", 0) or 0)
        response_headers = {
            str(key).casefold(): str(value) for key, value in dict(data.get("headers", {})).items()
        }
        rate = _rate_limit(response_headers)
        if status == 304:
            return GitHubAPIResponse(status_code=304, headers=response_headers, rate_limit=rate)
        if not result.ok:
            raise GitHubAPIError(
                _error_category(status, response_headers),
                status,
                remaining=rate.remaining,
                reset_at=rate.reset_at,
                retry_after_seconds=rate.retry_after_seconds,
            )
        raw_body = data.get("body", "")
        try:
            body = json.loads(str(raw_body)) if raw_body else None
        except json.JSONDecodeError as exc:
            raise GitHubAPIError("invalid_json", status) from exc
        return GitHubAPIResponse(
            status_code=status,
            body=body,
            headers=response_headers,
            rate_limit=rate,
        )


def _rate_limit(headers: dict[str, str]) -> RateLimitState:
    remaining = _integer(headers.get("x-ratelimit-remaining"))
    reset_epoch = _integer(headers.get("x-ratelimit-reset"))
    retry_after = _integer(headers.get("retry-after"))
    reset_at = datetime.fromtimestamp(reset_epoch, UTC) if reset_epoch else None
    if retry_after is not None and reset_at is None:
        reset_at = datetime.now(UTC) + timedelta(seconds=retry_after)
    return RateLimitState(
        remaining=remaining,
        reset_at=reset_at,
        retry_after_seconds=retry_after,
        request_id=headers.get("x-github-request-id", "")[:128],
    )


def _error_category(status: int, headers: dict[str, str]) -> str:
    if status == 401:
        return "token_invalid"
    if status == 404:
        return "repository_not_found"
    if status == 429:
        return "rate_limited"
    if status == 403:
        if headers.get("retry-after") or headers.get("x-ratelimit-remaining") == "0":
            return "rate_limited"
        return "permission_denied"
    return f"github_http_{status}" if status else "http_failed"


def _integer(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def as_mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}

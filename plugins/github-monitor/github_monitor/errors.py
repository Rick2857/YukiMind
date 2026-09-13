"""Typed GitHub Monitor failures."""

from __future__ import annotations

from datetime import datetime


class GitHubMonitorError(RuntimeError):
    pass


class GitHubAPIError(GitHubMonitorError):
    def __init__(
        self,
        category: str,
        status_code: int = 0,
        *,
        remaining: int | None = None,
        reset_at: datetime | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(category)
        self.category = category
        self.status_code = status_code
        self.remaining = remaining
        self.reset_at = reset_at
        self.retry_after_seconds = retry_after_seconds

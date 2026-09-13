"""Redacted MCP lifecycle event records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MCPEvent:
    server_id: str
    event: str
    success: bool
    error_category: str | None
    occurred_at: datetime

"""Stable, secret-free diagnostics for MCP failures."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class MCPFailureDisposition:
    code: str
    public_message: str
    retryable: bool
    disconnect: bool


# Compatibility for integrations that imported the 2.1 name.
MCPErrorDetails = MCPFailureDisposition


def classify_mcp_exception(exc: Exception) -> MCPFailureDisposition:
    """Classify a call failure separately from connection invalidation."""

    errors = tuple(_walk_exceptions(exc))
    status = next(
        (candidate for item in errors if (candidate := _http_status(item)) is not None),
        None,
    )
    if status in {401, 403}:
        return MCPFailureDisposition(
            "mcp_authentication_failed",
            "MCP 鉴权失败，请检查 Token 是否有效",
            False,
            False,
        )
    if status == 429:
        return MCPFailureDisposition(
            "mcp_rate_limited",
            "MCP 服务请求过于频繁，请稍后重试",
            True,
            False,
        )
    if status is not None and status >= 500:
        return MCPFailureDisposition(
            "mcp_server_unavailable",
            "MCP 服务暂时不可用",
            True,
            False,
        )
    if status is not None:
        return MCPFailureDisposition(
            f"mcp_http_{status}",
            "MCP 服务拒绝了请求",
            False,
            False,
        )
    if any(isinstance(item, (TimeoutError, httpx.TimeoutException)) for item in errors):
        return MCPFailureDisposition(
            "mcp_timeout",
            "MCP 工具调用超时",
            True,
            False,
        )
    if any(isinstance(item, (OSError, httpx.TransportError)) for item in errors):
        return MCPFailureDisposition(
            "mcp_transport_unavailable",
            "MCP 服务暂时不可用",
            True,
            True,
        )
    combined = " ".join(str(item).casefold() for item in errors)
    disconnect = any(
        marker in combined
        for marker in (
            "invalid session",
            "session expired",
            "protocol error",
            "protocol failure",
            "initialization failed",
            "not initialized",
        )
    )
    return MCPFailureDisposition(
        type(exc).__name__,
        "MCP 工具暂时不可用",
        False,
        disconnect,
    )


def _walk_exceptions(exc: Exception) -> Iterator[Exception]:
    pending = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        yield current
        if isinstance(current, ExceptionGroup):
            pending.extend(
                item for item in reversed(current.exceptions) if isinstance(item, Exception)
            )
        cause = current.__cause__ or current.__context__
        if isinstance(cause, Exception):
            pending.append(cause)


def _http_status(exc: Exception) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None

"""Convert MCP SDK content blocks into the unified kernel result."""

from __future__ import annotations

import json
from typing import Any

from qq_ai_bot.capabilities.results import ToolExecutionResult
from qq_ai_bot.mcp.redaction import redact_sensitive_data, redact_sensitive_text


def normalize_mcp_result(value: Any, *, server_id: str, tool_name: str) -> ToolExecutionResult:
    structured = getattr(value, "structuredContent", None)
    is_error = bool(getattr(value, "isError", False))
    content: list[dict[str, Any]] = []
    public_error = ""
    upstream_error_code = ""
    retryable = False
    for item in getattr(value, "content", ()):
        if hasattr(item, "model_dump"):
            dumped = item.model_dump(mode="json", exclude_none=True)
            normalized = dict(dumped) if isinstance(dumped, dict) else {"value": dumped}
        else:
            normalized = {"value": str(item)}
        # MCP servers commonly mirror structuredContent into a large text block for
        # backwards-compatible clients. Keeping both can double the payload and make
        # the result budgeter discard the useful structured data. On successful
        # structured results, retain only non-text blocks such as images/resources.
        if structured is not None and not is_error and normalized.get("type") == "text":
            continue
        if is_error and normalized.get("type") == "text":
            parsed_error = _parse_structured_error(normalized.get("text"))
            if parsed_error is not None:
                upstream_error_code, public_error, retryable = parsed_error
        content.append(redact_sensitive_data(normalized))

    if structured is None and not is_error:
        promoted, content = _promote_single_json_text(content)
        if promoted is not None:
            structured = promoted
    content = _redact_text_blocks(content)
    structured = redact_sensitive_data(structured)
    public_error = redact_sensitive_text(public_error)
    return ToolExecutionResult(
        ok=not is_error,
        data=structured,
        content=tuple(content),
        error_code="mcp_tool_error" if is_error else None,
        public_message=(public_error or "MCP 工具返回错误") if is_error else None,
        retryable=retryable,
        mutation_committed=False if is_error else None,
        provider_id=f"mcp.{server_id}",
        tool_name=tool_name,
        metadata={
            "mcp_is_error": is_error,
            **({"mcp_error_code": upstream_error_code} if upstream_error_code else {}),
        },
    )


def _promote_single_json_text(
    content: list[dict[str, Any]],
) -> tuple[dict[str, Any] | list[Any] | None, list[dict[str, Any]]]:
    """Promote one complete JSON object/array text block to structured data."""

    text_indexes = [
        index
        for index, item in enumerate(content)
        if item.get("type") == "text" and isinstance(item.get("text"), str)
    ]
    if len(text_indexes) != 1:
        return None, content
    text_index = text_indexes[0]
    raw_text = str(content[text_index]["text"]).strip()
    try:
        decoded = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        content[text_index]["text"] = redact_sensitive_text(raw_text)
        return None, content
    if not isinstance(decoded, (dict, list)):
        content[text_index]["text"] = redact_sensitive_text(raw_text)
        return None, content
    remaining = content[:text_index] + content[text_index + 1 :]
    return redact_sensitive_data(decoded), remaining


def _redact_text_blocks(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    redacted: list[dict[str, Any]] = []
    for item in content:
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            item = {**item, "text": redact_sensitive_text(str(item["text"]))}
        redacted.append(item)
    return redacted


def _parse_structured_error(value: object) -> tuple[str, str, bool] | None:
    """Extract the bounded server error envelope used by MCP tool failures."""

    if not isinstance(value, str):
        return None
    opening = value.find("{")
    if opening < 0:
        return None
    try:
        payload = json.loads(value[opening:])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    message = redact_sensitive_text(" ".join(str(payload.get("message", "")).split())[:500])
    if not message:
        return None
    error_code = str(payload.get("error_code", "")).strip()[:64]
    retryable = payload.get("retryable") is True
    return error_code, message, retryable

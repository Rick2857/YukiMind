"""Load the single configured MCP file and resolve environment references centrally."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from qq_ai_bot.mcp.models import MCPConfigFile, MCPServerConfig

_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SERVER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class MCPConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LoadedMCPConfig:
    servers: dict[str, MCPServerConfig]
    hashes: dict[str, str]
    source_exists: bool


def load_mcp_config(
    path: Path,
    *,
    environment: Mapping[str, str] | None = None,
) -> LoadedMCPConfig:
    """Read only ``path``; a missing file is a valid empty configuration."""

    if not path.exists():
        return LoadedMCPConfig({}, {}, False)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MCPConfigurationError(f"cannot read MCP config: {type(exc).__name__}") from exc
    resolved = _expand(raw, environment or os.environ)
    try:
        parsed = MCPConfigFile.model_validate(resolved)
    except ValidationError as exc:
        raise MCPConfigurationError("invalid MCP configuration") from exc
    servers: dict[str, MCPServerConfig] = {}
    hashes: dict[str, str] = {}
    for server_id, server in parsed.mcp_servers.items():
        if not _SERVER_ID.fullmatch(server_id):
            raise MCPConfigurationError(f"invalid MCP server id: {server_id}")
        if server.cwd is not None and not server.cwd.is_absolute():
            server = server.model_copy(update={"cwd": (path.parent / server.cwd).resolve()})
        servers[server_id] = server
        canonical = json.dumps(server.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        hashes[server_id] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return LoadedMCPConfig(servers, hashes, True)


def _expand(value: Any, environment: Mapping[str, str]) -> Any:
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in environment:
                raise MCPConfigurationError(f"missing environment variable: {name}")
            return environment[name]

        return _ENV_REFERENCE.sub(replace, value)
    if isinstance(value, list):
        return [_expand(item, environment) for item in value]
    if isinstance(value, dict):
        return {str(key): _expand(item, environment) for key, item in value.items()}
    return value


def redacted_server_config(server: MCPServerConfig) -> dict[str, object]:
    """Return display-safe endpoint metadata for commands and logs."""

    return {
        "transport": server.transport.value,
        "lifecycle": server.lifecycle.value,
        "disabled": server.disabled,
        "scope": server.yuki.scope,
        "summary": server.yuki.summary,
        "tags": list(server.yuki.tags),
        "command": Path(server.command).name if server.command else None,
        "url_configured": server.url is not None,
        "header_names": sorted(server.headers),
        "environment_names": sorted(server.env),
        "include_tools": list(server.include_tools),
        "exclude_tools": list(server.exclude_tools),
        "tool_annotation_overrides": sorted(server.yuki.tool_annotations),
        "tool_bundles": {
            name: {
                "scope": bundle.scope,
                "summary": bundle.summary,
                "include_tools": list(bundle.include_tools),
            }
            for name, bundle in server.yuki.tool_bundles.items()
        },
        "automation": {
            "enabled": server.yuki.automation.enabled,
            "permission": server.yuki.automation.permission,
            "include_tools": list(server.yuki.automation.include_tools),
        },
        "reconnect_delay_seconds": server.reconnect_delay_seconds,
    }

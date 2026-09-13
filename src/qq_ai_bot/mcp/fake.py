"""Offline fakes for MCP integration and downstream plugin tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FakeMCPConnection:
    tools: tuple[Any, ...] = ()
    results: dict[str, Any] = field(default_factory=dict)
    fail_connect: bool = False
    calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)
    _connected: bool = False
    _tools_changed_callback: Callable[[], Awaitable[None]] | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def server_info(self) -> dict[str, str]:
        return {
            "protocol_version": "fake",
            "server_name": "FakeMCPServer",
            "server_version": "1",
        }

    async def connect(self) -> None:
        if self.fail_connect:
            raise OSError("fake connection failure")
        self._connected = True

    async def list_tools(self) -> tuple[Any, ...]:
        return self.tools

    async def call_tool(self, name: str, arguments: dict[str, object]) -> Any:
        self.calls.append((name, arguments))
        if name not in self.results:
            raise RuntimeError("unknown fake MCP tool")
        return self.results[name]

    async def close(self) -> None:
        self._connected = False

    def set_tools_changed_callback(self, callback: Callable[[], Awaitable[None]]) -> None:
        self._tools_changed_callback = callback

    async def notify_tools_changed(self) -> None:
        if self._tools_changed_callback is not None:
            await self._tools_changed_callback()

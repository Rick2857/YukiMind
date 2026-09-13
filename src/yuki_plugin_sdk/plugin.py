"""Plugin lifecycle protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from yuki_plugin_sdk.context import PluginContext
from yuki_plugin_sdk.registrar import PluginRegistrar


@runtime_checkable
class Plugin(Protocol):
    async def register(self, registrar: PluginRegistrar) -> None: ...

    async def start(self, context: PluginContext) -> None: ...

    async def stop(self) -> None: ...

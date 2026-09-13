"""Timeout-bounded, failure-isolated notification Hook execution."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from yuki_plugin_sdk.errors import RegistrationError
from yuki_plugin_sdk.events import (
    EventEnvelope,
    EventName,
    HookExecution,
    NotificationHandler,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Subscription:
    plugin_id: str
    hook_id: str
    event: EventName
    handler: NotificationHandler
    priority: int
    timeout_seconds: float | None


class PluginEventBus:
    def __init__(self, *, default_timeout_seconds: float = 3.0) -> None:
        if default_timeout_seconds <= 0:
            raise ValueError("default hook timeout must be positive")
        self._default_timeout = default_timeout_seconds
        self._subscriptions: dict[tuple[str, str], _Subscription] = {}

    def configure_default_timeout(self, timeout_seconds: float) -> None:
        """Apply the HOT default to hooks that did not declare their own timeout."""

        if timeout_seconds <= 0:
            raise ValueError("default hook timeout must be positive")
        self._default_timeout = timeout_seconds

    def subscribe(
        self,
        *,
        plugin_id: str,
        hook_id: str,
        event: EventName,
        handler: NotificationHandler,
        priority: int = 0,
        timeout_seconds: float | None = None,
    ) -> None:
        key = (plugin_id, hook_id)
        if key in self._subscriptions:
            raise RegistrationError(f"duplicate event hook: {plugin_id}:{hook_id}")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("hook timeout must be positive")
        self._subscriptions[key] = _Subscription(
            plugin_id=plugin_id,
            hook_id=hook_id,
            event=event,
            handler=handler,
            priority=priority,
            timeout_seconds=timeout_seconds,
        )

    def unsubscribe_plugin(self, plugin_id: str) -> int:
        keys = [key for key in self._subscriptions if key[0] == plugin_id]
        for key in keys:
            del self._subscriptions[key]
        return len(keys)

    async def publish(self, event: EventEnvelope) -> tuple[HookExecution, ...]:
        subscriptions = sorted(
            (item for item in self._subscriptions.values() if item.event is event.name),
            key=lambda item: (-item.priority, item.plugin_id, item.hook_id),
        )
        if not subscriptions:
            return ()
        executions = await asyncio.gather(
            *(self._execute(item, event.model_copy(deep=True)) for item in subscriptions)
        )
        return tuple(executions)

    async def _execute(self, subscription: _Subscription, event: EventEnvelope) -> HookExecution:
        started = time.perf_counter()
        error_category: str | None = None
        timeout_seconds = subscription.timeout_seconds or self._default_timeout
        try:
            async with asyncio.timeout(timeout_seconds):
                await subscription.handler(event)
        except TimeoutError:
            error_category = "hook_timeout"
        except Exception as exc:
            error_category = type(exc).__name__
        duration = time.perf_counter() - started
        if error_category is not None:
            logger.warning(
                "plugin_hook_failed plugin_id=%s hook_id=%s event=%s error_category=%s",
                subscription.plugin_id,
                subscription.hook_id,
                event.name.value,
                error_category,
            )
        elif duration >= timeout_seconds * 0.8:
            logger.warning(
                "plugin_hook_slow plugin_id=%s hook_id=%s event=%s duration_seconds=%.4f",
                subscription.plugin_id,
                subscription.hook_id,
                event.name.value,
                duration,
            )
        return HookExecution(
            plugin_id=subscription.plugin_id,
            hook_id=subscription.hook_id,
            success=error_category is None,
            duration_seconds=duration,
            error_category=error_category,
        )

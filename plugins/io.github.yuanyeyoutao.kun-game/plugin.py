"""Thin Yuki Plugin API adapter for the deterministic Kun game engine."""

from __future__ import annotations

import asyncio
import importlib.util
import random
import secrets
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel, Field, ValidationError

from yuki_plugin_sdk.context import PluginContext
from yuki_plugin_sdk.models import JsonValue, PermissionLevel, StrictModel
from yuki_plugin_sdk.registrar import (
    CommandMetadata,
    CommandRegistration,
    PluginRegistrar,
)
from yuki_plugin_sdk.results import CommandResult

if TYPE_CHECKING:
    import engine as _engine
else:
    _engine = cast("ModuleType", None)

PLUGIN_ID = "io.github.yuanyeyoutao.kun-game"
STATE_NAMESPACE = "state"
CAS_ATTEMPTS = 3  # initial attempt plus the two retries required by the contract


def _load_engine() -> ModuleType:
    module_name = f"{__name__}.engine"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        module_name,
        Path(__file__).with_name("engine.py"),
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Kun game engine could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


if not TYPE_CHECKING:
    _engine = _load_engine()


class KunGameConfig(StrictModel):
    default_jie_cao: int = Field(default=50, ge=0, le=10**9)
    default_luck: int = Field(default=50, ge=0, le=100)
    egg_price: int = Field(default=5, ge=1, le=10**9)
    tribulation_cost: int = Field(default=10, ge=1, le=10**9)
    train_daily_max: int = Field(default=30, ge=1, le=1000)
    hatch_misfortune_rate: float = Field(default=0.007, ge=0, le=1)

    def engine_config(self) -> _engine.GameConfig:
        return _engine.GameConfig.from_mapping(self.model_dump())


class GameArguments(StrictModel):
    text: str = Field(default="", max_length=1000)


_CONFIG_KEYS = {
    "初始节操": "default_jie_cao",
    "初始运势": "default_luck",
    "蛋价": "egg_price",
    "渡劫消耗": "tribulation_cost",
    "每日磨炼上限": "train_daily_max",
    "悲属性孵化率": "hatch_misfortune_rate",
    **{name: name for name in KunGameConfig.model_fields},
}


class KunGamePlugin:
    def __init__(self) -> None:
        self._context: PluginContext | None = None
        # ponytail: this grows with seen scopes; prune only if high-churn deployments need it.
        self._scope_locks: dict[str, asyncio.Lock] = {}

    async def register(self, registrar: PluginRegistrar) -> None:
        registrar.register_config_schema(KunGameConfig)
        registrar.register_command(
            CommandRegistration(
                metadata=CommandMetadata(
                    name="play",
                    description="执行一个普通养鲲游戏动作或小游戏答案。",
                    permission=PermissionLevel.USER,
                    timeout_seconds=10,
                ),
                argument_model=GameArguments,
                handler=self._play,
            )
        )
        registrar.register_command(
            CommandRegistration(
                metadata=CommandMetadata(
                    name="admin",
                    description="由真实 Yuki SUPERUSER 执行养鲲管理或经济配置动作。",
                    permission=PermissionLevel.SUPERUSER,
                    timeout_seconds=10,
                ),
                argument_model=GameArguments,
                handler=self._admin,
            )
        )

    async def start(self, context: PluginContext) -> None:
        context.features.require("message.current.mentions.v1")
        self._context = context

    async def stop(self) -> None:
        self._context = None
        self._scope_locks.clear()
        sys.modules.pop(f"{__name__}.engine", None)

    async def _play(self, raw_arguments: BaseModel) -> CommandResult:
        arguments = GameArguments.model_validate(raw_arguments.model_dump())
        return await self._execute(arguments.text, admin=False)

    async def _admin(self, raw_arguments: BaseModel) -> CommandResult:
        arguments = GameArguments.model_validate(raw_arguments.model_dump())
        return await self._execute(arguments.text, admin=True)

    async def _execute(self, text: str, *, admin: bool) -> CommandResult:
        context = self._running_context()
        try:
            current = await context.messages.get_current()
        except Exception as exc:
            context.logger.warning("kun game current-message lookup failed: %s", type(exc).__name__)
            return _error("kun_game.context_unavailable", "无法读取当前可信消息上下文。")
        if current is None:
            return _error("kun_game.no_current_message", "当前没有可执行游戏命令的消息。")
        if current.scope_type == "group":
            if not current.group_id:
                return _error("kun_game.invalid_scope", "群消息缺少可信群号。")
            scope_id = current.group_id
        elif current.scope_type == "private":
            scope_id = current.sender_user_id
        else:
            return _error("kun_game.invalid_scope", "消息作用域无效。")
        game_scope = cast("_engine.ScopeType", current.scope_type)
        if admin and current.scope_type != "group":
            return _error("kun_game.admin_group_only", "管理命令仅支持群聊。")

        display_name = await self._display_name(context, current.sender_user_id)
        try:
            plugin_config = await self._effective_config(context, current.scope_type, scope_id)
        except (ValueError, ValidationError) as exc:
            context.logger.warning("kun game config invalid: %s", type(exc).__name__)
            return _error("kun_game.config_invalid", "养鲲经济配置无效，请联系管理员。")
        except Exception as exc:
            context.logger.warning("kun game config unavailable: %s", type(exc).__name__)
            return _error("kun_game.config_unavailable", "暂时无法读取养鲲经济配置。")

        command = text.strip().removeprefix("*").strip().split(maxsplit=1)
        if admin and command and command[0] == "配置":
            return await self._configure(context, current.scope_type, scope_id, text, plugin_config)

        scope_key = f"{current.scope_type}:{scope_id}"
        lock = self._scope_locks.setdefault(scope_key, asyncio.Lock())
        command_time = current.received_at
        seed = secrets.randbits(64)
        async with lock:
            for attempt in range(CAS_ATTEMPTS):
                try:
                    old_value = await context.storage.get(STATE_NAMESPACE, scope_key)
                    if old_value is not None and not isinstance(old_value, dict):
                        raise _engine.StateValidationError("stored envelope is not an object")
                    old_envelope = cast("Mapping[str, object] | None", old_value)
                    if admin:
                        result = _engine.execute_admin(
                            old_envelope,
                            text=text,
                            user_id=current.sender_user_id,
                            display_name=display_name,
                            scope_type=game_scope,
                            scope_id=scope_id,
                            rng=random.Random(seed),
                            now=command_time,
                            config=plugin_config.engine_config(),
                        )
                    else:
                        result = _engine.execute_play(
                            old_envelope,
                            text=text,
                            user_id=current.sender_user_id,
                            display_name=display_name,
                            scope_type=game_scope,
                            scope_id=scope_id,
                            mentioned_user_ids=current.mentioned_user_ids,
                            rng=random.Random(seed),
                            now=command_time,
                            config=plugin_config.engine_config(),
                        )
                except _engine.StateValidationError as exc:
                    revision = old_value.get("revision") if isinstance(old_value, dict) else None
                    context.logger.error(
                        "kun game state validation failed scope=%s revision=%s type=%s",
                        scope_key,
                        revision,
                        type(exc).__name__,
                    )
                    return _error("kun_game.state_corrupt", "养鲲状态校验失败，未覆盖原数据。")
                except Exception as exc:
                    context.logger.error(
                        "kun game storage or execution failed scope=%s type=%s",
                        scope_key,
                        type(exc).__name__,
                    )
                    return _error("kun_game.execution_failed", "养鲲命令执行失败，状态未确认写入。")

                if not result.changed:
                    return CommandResult(
                        text=result.text,
                        data={"scope": scope_key, "revision": _revision(result.envelope)},
                    )
                if result.envelope is None:
                    return _error("kun_game.execution_failed", "游戏引擎未返回可提交状态。")
                try:
                    changed = await context.storage.compare_and_set(
                        STATE_NAMESPACE,
                        scope_key,
                        cast(JsonValue, old_value),
                        cast(JsonValue, result.envelope),
                    )
                except Exception as exc:
                    context.logger.error(
                        "kun game storage write failed scope=%s type=%s",
                        scope_key,
                        type(exc).__name__,
                    )
                    return _error("kun_game.storage_unavailable", "养鲲状态暂时无法写入。")
                if changed:
                    return CommandResult(
                        text=result.text,
                        data={"scope": scope_key, "revision": _revision(result.envelope)},
                    )
                context.logger.warning(
                    "kun game CAS conflict scope=%s attempt=%d",
                    scope_key,
                    attempt + 1,
                )
        return _error("kun_game.cas_conflict", "本群状态正在频繁变化，请稍后重试。")

    async def _effective_config(
        self, context: PluginContext, scope_type: str, scope_id: str
    ) -> KunGameConfig:
        values = KunGameConfig().model_dump()
        scoped_type = "group" if scope_type == "group" else "user"
        for key in KunGameConfig.model_fields:
            global_value = await context.config.get(key, scope_type="global")
            if global_value is not None:
                values[key] = global_value
            scoped_value = await context.config.get(
                key,
                scope_type=scoped_type,
                scope_id=scope_id,
            )
            if scoped_value is not None:
                values[key] = scoped_value
        return KunGameConfig.model_validate(values)

    async def _configure(
        self,
        context: PluginContext,
        scope_type: str,
        scope_id: str,
        text: str,
        current: KunGameConfig,
    ) -> CommandResult:
        if scope_type != "group":
            return _error("kun_game.admin_group_only", "配置管理仅支持群聊。")
        parts = text.strip().removeprefix("*").strip().split()
        if len(parts) == 1:
            values = "\n".join(f"{key}={value}" for key, value in current.model_dump().items())
            return CommandResult(text=f"当前群养鲲经济配置：\n{values}")
        if len(parts) != 3 or parts[1] not in _CONFIG_KEYS:
            return _error(
                "kun_game.config_usage",
                "格式：配置 <配置项> <数值>；发送“配置”查看配置项。",
            )
        key = _CONFIG_KEYS[parts[1]]
        try:
            value: int | float = (
                float(parts[2]) if key == "hatch_misfortune_rate" else int(parts[2])
            )
            candidate = KunGameConfig.model_validate({**current.model_dump(), key: value})
            await context.config.set(
                key,
                cast(JsonValue, getattr(candidate, key)),
                scope_type="group",
                scope_id=scope_id,
            )
        except (ValueError, ValidationError):
            return _error("kun_game.config_invalid", "配置值无效或超出允许范围。")
        except Exception as exc:
            context.logger.error("kun game config write failed: %s", type(exc).__name__)
            return _error("kun_game.config_unavailable", "配置暂时无法写入。")
        return CommandResult(text=f"本群配置已更新：{key}={getattr(candidate, key)}")

    async def _display_name(self, context: PluginContext, user_id: str) -> str:
        try:
            profile = await context.people.get_current()
            if profile is not None:
                display_name = profile.get("display_name")
                if isinstance(display_name, str) and display_name.strip():
                    return display_name.strip()[:128]
        except Exception as exc:
            context.logger.warning("kun game display-name lookup failed: %s", type(exc).__name__)
        return user_id

    def _running_context(self) -> PluginContext:
        if self._context is None:
            raise RuntimeError("Kun game plugin is not running")
        return self._context


def _revision(envelope: Mapping[str, object] | None) -> int:
    if envelope is None:
        return 0
    revision = envelope.get("revision")
    return revision if isinstance(revision, int) and not isinstance(revision, bool) else 0


def _error(code: str, text: str) -> CommandResult:
    return CommandResult(ok=False, error_code=code, text=text, detail=text)


__all__ = ["GameArguments", "KunGameConfig", "KunGamePlugin"]

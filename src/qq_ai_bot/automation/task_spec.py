"""Provider-neutral high-level automation task contract."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from qq_ai_bot.automation.models import AutomationContext, Schedule, StrictModel


class TaskStrategy(StrEnum):
    AUTO = "auto"
    STATIC = "static"
    GENERATED = "generated"
    AGENTIC = "agentic"


class TaskDelivery(StrictModel):
    target: Literal["auto", "self_private", "current_group", "none"] = "auto"
    text: str | None = Field(default=None, min_length=1, max_length=12000)


class TaskSpec(StrictModel):
    """Small intent contract shared by conversational and scheduled Agents."""

    version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=128)
    goal: str = Field(min_length=1, max_length=2500)
    trigger: Schedule
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    strategy: TaskStrategy = Field(
        default=TaskStrategy.AUTO,
        description=(
            "纯提醒用 static；运行时需要模型或工具时用 agentic。auto 仅在显式选择能力时"
            "自动进入 agentic。"
        ),
    )
    capabilities: tuple[str, ...] = Field(
        default=(),
        max_length=128,
        description=(
            "agentic 下省略或留空表示继承创建者当前可委托工具域；显式列出时只用于主动缩小"
            "工具域，不必预判完整调用链。"
        ),
    )
    constraints: tuple[str, ...] = Field(default=(), max_length=12)
    context: AutomationContext = Field(default_factory=AutomationContext)
    delivery: TaskDelivery = Field(default_factory=TaskDelivery)

    @model_validator(mode="after")
    def _strategy_matches_capabilities(self) -> TaskSpec:
        if self.strategy in {TaskStrategy.STATIC, TaskStrategy.GENERATED} and self.capabilities:
            raise ValueError(f"{self.strategy.value} 策略不能声明外部 capability")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("capabilities 不能重复")
        return self

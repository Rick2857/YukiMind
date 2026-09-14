"""Persona-bound L1 adaptive behavior rules backed by SELF memory."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from qq_ai_bot.config import Settings
from qq_ai_bot.domain.conversations import ScopeType
from qq_ai_bot.domain.messages import InboundMessage
from qq_ai_bot.memory.enums import (
    MemoryKind,
    MemoryScopeType,
    MemoryStatus,
    SelfMemoryVisibility,
)
from qq_ai_bot.memory.models import MemoryFact, MemoryFactQuery
from qq_ai_bot.memory.service import MemoryFactService

_RULE_PREFIX = "adaptive_behavior:v1:"
_RULE_KEY = re.compile(
    r"^adaptive_behavior:v1:(?P<persona>[0-9a-f]{64}):"
    r"(?P<dimension>response_length|explanation_style|initiative)$"
)

BEHAVIOR_OPTIONS: dict[str, dict[str, str]] = {
    "response_length": {
        "concise": "默认简短作答，只保留解决当前问题所需的信息。",
        "balanced": "默认采用适中篇幅，兼顾结论和必要说明。",
        "detailed": "默认给出较完整的解释和关键细节。",
    },
    "explanation_style": {
        "direct": "默认先直接给结论，仅在必要时补充解释。",
        "balanced": "默认先给结论，再补充简洁理由。",
        "step_by_step": "遇到有步骤的任务时，默认按顺序解释关键步骤。",
    },
    "initiative": {
        "reactive": "默认只处理明确提出的请求，不主动扩展额外事项。",
        "balanced": "默认完成请求，并只补充明显有帮助的一项提醒。",
        "proactive": "默认主动指出紧邻的风险、遗漏或下一步。",
    },
}


@dataclass(frozen=True, slots=True)
class AdaptiveBehaviorRule:
    fact_id: int
    persona_id: str
    dimension: str
    value: str
    instruction: str
    status: MemoryStatus
    visibility: SelfMemoryVisibility

    def to_prompt_data(self) -> dict[str, str]:
        return {
            "dimension": self.dimension,
            "default": self.value,
            "guidance": self.instruction,
        }


def persona_fingerprint(system_prompt: str) -> str:
    """Fingerprint the resolved prompt so persona edits invalidate old L1 defaults."""

    return hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()


def adaptive_behavior_key(persona_id: str, dimension: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", persona_id):
        raise ValueError("adaptive behavior persona id must be a SHA-256 digest")
    if dimension not in BEHAVIOR_OPTIONS:
        raise ValueError("unsupported adaptive behavior dimension")
    return f"{_RULE_PREFIX}{persona_id}:{dimension}"


def is_adaptive_behavior_key(memory_key: str | None) -> bool:
    return bool(memory_key and memory_key.startswith(_RULE_PREFIX))


def parse_adaptive_behavior_fact(fact: MemoryFact) -> AdaptiveBehaviorRule | None:
    if not is_adaptive_behavior_key(fact.memory_key):
        return None
    match = _RULE_KEY.fullmatch(fact.memory_key)
    if match is None:
        raise ValueError("malformed adaptive behavior memory key")
    if fact.scope_type is not MemoryScopeType.SELF:
        raise ValueError("adaptive behavior must use SELF scope")
    if fact.category != "self_preference" or fact.kind is not MemoryKind.PREFERENCE:
        raise ValueError("adaptive behavior must be a SELF preference")
    if fact.visibility_type is None:
        raise ValueError("adaptive behavior requires SELF visibility")
    dimension = match.group("dimension")
    value = fact.content.strip()
    instruction = BEHAVIOR_OPTIONS[dimension].get(value)
    if instruction is None:
        raise ValueError("unsupported adaptive behavior value")
    return AdaptiveBehaviorRule(
        fact_id=fact.id,
        persona_id=match.group("persona"),
        dimension=dimension,
        value=value,
        instruction=instruction,
        status=fact.status,
        visibility=fact.visibility_type,
    )


def validate_adaptive_behavior_change(
    *,
    operation: str,
    memory_key: str | None,
    content: str | None,
    category: str | None,
    kind: MemoryKind | None,
    visibility: str,
    evidence_refs: tuple[str, ...],
    current_persona_id: str,
) -> bool:
    """Validate an L1 proposal; return False when it is not an L1 proposal."""

    if not is_adaptive_behavior_key(memory_key):
        return False
    match = _RULE_KEY.fullmatch(memory_key or "")
    if match is None:
        raise ValueError("malformed adaptive behavior memory key")
    if match.group("persona") != current_persona_id:
        raise ValueError("adaptive behavior proposal targets a stale persona")
    if operation not in {"create", "correct", "invalidate"}:
        raise ValueError("adaptive behavior only supports create, correct, or invalidate")
    if visibility != "current_scope":
        raise ValueError("adaptive behavior cannot become global")
    if len(set(evidence_refs)) < 2:
        raise ValueError("adaptive behavior requires at least two evidence references")
    if operation in {"create", "correct"}:
        dimension = match.group("dimension")
        if content is None or content.strip() not in BEHAVIOR_OPTIONS[dimension]:
            raise ValueError("unsupported adaptive behavior value")
    if operation == "create" and (
        category != "self_preference" or kind is not MemoryKind.PREFERENCE
    ):
        raise ValueError("adaptive behavior creation requires a SELF preference")
    return True


def adaptive_behavior_reflection_instruction(persona_id: str) -> str:
    keys = ", ".join(
        f"{dimension}={','.join(values)}" for dimension, values in BEHAVIOR_OPTIONS.items()
    )
    return (
        "L1 行为自适应只能记录用户对回答方式的稳定反馈，不能定义身份、语气、人际关系、事实、"
        "安全边界或工具权限。只有用户明确要求以后持续采用某种方式，或至少两条独立事件反复支持"
        "同一偏好时，才可 create/correct/invalidate L1 规则。每条规则必须使用至少两个真实 "
        "event_N/tool_N evidence_refs，只能 current_scope，category=self_preference，"
        "kind=preference。"
        f"当前 persona_id={persona_id}。memory_key 必须是 "
        f"adaptive_behavior:v1:{persona_id}:<dimension>，content 必须是以下枚举之一：{keys}。"
        "不要创建或修改其他 persona_id 的规则。本轮明确要求和共享核心人格始终优先于 L1 默认值。"
    )


class AdaptiveBehaviorService:
    """Read validated L1 rules from existing versioned SELF memory."""

    def __init__(self, *, settings: Settings, memories: MemoryFactService) -> None:
        self._memories = memories
        self.persona_id = persona_fingerprint(settings.system_prompt)

    async def prompt_rules(self, message: InboundMessage) -> tuple[dict[str, str], ...]:
        facts = await self.visible_facts(message, status=MemoryStatus.ACTIVE)
        local: dict[str, AdaptiveBehaviorRule] = {}
        global_rules: dict[str, AdaptiveBehaviorRule] = {}
        for fact in facts:
            try:
                rule = parse_adaptive_behavior_fact(fact)
            except ValueError:
                continue
            if rule is None or rule.persona_id != self.persona_id:
                continue
            target = global_rules if rule.visibility is SelfMemoryVisibility.GLOBAL else local
            target.setdefault(rule.dimension, rule)
        selected = {**global_rules, **local}
        return tuple(selected[key].to_prompt_data() for key in sorted(selected))

    async def visible_facts(
        self,
        message: InboundMessage,
        *,
        status: MemoryStatus,
    ) -> tuple[MemoryFact, ...]:
        global_rows = await self._memories.repository.list_facts(
            MemoryFactQuery(
                scope_type=MemoryScopeType.SELF,
                visibility_type=SelfMemoryVisibility.GLOBAL,
                status=status,
            ),
            limit=50,
        )
        if message.scope_type is ScopeType.GROUP and message.group_id is not None:
            local_query = MemoryFactQuery(
                scope_type=MemoryScopeType.SELF,
                visibility_type=SelfMemoryVisibility.GROUP,
                visibility_group_id=message.group_id,
                status=status,
            )
        else:
            local_query = MemoryFactQuery(
                scope_type=MemoryScopeType.SELF,
                visibility_type=SelfMemoryVisibility.PRIVATE,
                visibility_user_id=message.sender.user_id,
                status=status,
            )
        local_rows = await self._memories.repository.list_facts(local_query, limit=50)
        return tuple(
            fact
            for fact in (*local_rows, *global_rows)
            if is_adaptive_behavior_key(fact.memory_key)
        )

    async def active_version(self, fact: MemoryFact) -> MemoryFact | None:
        query = MemoryFactQuery(
            scope_type=MemoryScopeType.SELF,
            visibility_type=fact.visibility_type,
            visibility_user_id=fact.visibility_user_id,
            visibility_group_id=fact.visibility_group_id,
            status=MemoryStatus.ACTIVE,
        )
        rows = await self._memories.repository.list_facts(query, limit=50)
        return next((row for row in rows if row.memory_key == fact.memory_key), None)

    async def get_rule_fact(self, fact_id: int) -> MemoryFact | None:
        fact = await self._memories.get_fact(fact_id)
        if fact is None or not is_adaptive_behavior_key(fact.memory_key):
            return None
        parse_adaptive_behavior_fact(fact)
        return fact

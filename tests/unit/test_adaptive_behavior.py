"""L1 adaptive behavior stays bounded to the active core persona."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from tests.conftest import make_settings

from qq_ai_bot.domain.conversations import ScopeType
from qq_ai_bot.domain.messages import ChatMessage, InboundMessage, SenderIdentity
from qq_ai_bot.memory.adaptive_behavior import (
    AdaptiveBehaviorService,
    adaptive_behavior_key,
    parse_adaptive_behavior_fact,
    persona_fingerprint,
    validate_adaptive_behavior_change,
)
from qq_ai_bot.memory.enums import (
    MemoryAuthority,
    MemoryKind,
    MemoryScopeType,
    MemorySourceType,
    MemoryStatus,
    SelfMemoryVisibility,
)
from qq_ai_bot.memory.models import MemoryFact, MemoryFactCreate
from qq_ai_bot.memory.repository import MemoryFactRepository
from qq_ai_bot.memory.service import MemoryFactService
from qq_ai_bot.persistence.database import Database
from qq_ai_bot.services.context_assembler import AssembledContext, ContextMetrics
from qq_ai_bot.services.prompt_composer import PromptComposer
from qq_ai_bot.time.models import TimeContext


def _fact(*, persona_id: str, content: str = "concise", fact_id: int = 1) -> MemoryFact:
    now = datetime(2026, 9, 14, tzinfo=UTC)
    return MemoryFact(
        id=fact_id,
        scope_type=MemoryScopeType.SELF,
        visibility_type=SelfMemoryVisibility.PRIVATE,
        visibility_user_id="1001",
        kind=MemoryKind.PREFERENCE,
        memory_key=adaptive_behavior_key(persona_id, "response_length"),
        category="self_preference",
        content=content,
        normalized_content=content,
        importance=3,
        confidence=0.9,
        source_type=MemorySourceType.AUTOMATIC,
        authority=MemoryAuthority.AGENT_REFLECTION,
        status=MemoryStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


class _StubMemoryRepository:
    def __init__(self, facts: tuple[MemoryFact, ...]) -> None:
        self._facts = facts

    async def list_facts(self, query: object, *, limit: int) -> tuple[MemoryFact, ...]:
        return self._facts


class _StubMemoryService:
    def __init__(self, facts: tuple[MemoryFact, ...]) -> None:
        self.repository = _StubMemoryRepository(facts)


def _inbound() -> InboundMessage:
    return InboundMessage(
        message_id="rsi-1",
        event_type="message:test",
        scope_type=ScopeType.PRIVATE,
        sender=SenderIdentity("1001"),
        text="在吗",
        bot_user_id="9999",
    )


def test_persona_change_makes_old_l1_rule_stale() -> None:
    old_persona = persona_fingerprint("old persona")
    new_persona = persona_fingerprint("new persona")
    rule = parse_adaptive_behavior_fact(_fact(persona_id=old_persona))

    assert rule is not None
    assert rule.persona_id == old_persona
    assert rule.persona_id != new_persona


@pytest.mark.asyncio
async def test_persona_change_stops_injecting_old_l1_rules() -> None:
    old_persona = persona_fingerprint("old persona")
    settings = make_settings(
        "sqlite+aiosqlite:///:memory:",
        system_prompt="新人格",
        system_prompt_file=None,
    )
    current_persona = persona_fingerprint(settings.system_prompt)

    assert current_persona != old_persona

    stale_only = AdaptiveBehaviorService(
        settings=settings,
        memories=_StubMemoryService((_fact(persona_id=old_persona),)),  # type: ignore[arg-type]
    )
    assert await stale_only.prompt_rules(_inbound()) == ()

    current = AdaptiveBehaviorService(
        settings=settings,
        memories=_StubMemoryService(
            (
                _fact(persona_id=old_persona, content="detailed"),
                _fact(persona_id=current_persona, fact_id=2),
            )
        ),  # type: ignore[arg-type]
    )
    rules = await current.prompt_rules(_inbound())

    assert [rule["default"] for rule in rules] == ["concise"]


@pytest.mark.asyncio
async def test_l1_rule_round_trips_through_self_memory(database: Database) -> None:
    settings = make_settings(database.url, system_prompt="人格", system_prompt_file=None)
    persona_id = persona_fingerprint(settings.system_prompt)
    memories = MemoryFactService(MemoryFactRepository(database))
    fact = await memories.remember(
        MemoryFactCreate(
            scope_type=MemoryScopeType.SELF,
            visibility_type=SelfMemoryVisibility.PRIVATE,
            visibility_user_id="1001",
            kind=MemoryKind.PREFERENCE,
            memory_key=adaptive_behavior_key(persona_id, "initiative"),
            category="self_preference",
            content="balanced",
            importance=3,
            confidence=0.9,
            source_type=MemorySourceType.AUTOMATIC,
            authority=MemoryAuthority.AGENT_REFLECTION,
        )
    )

    service = AdaptiveBehaviorService(settings=settings, memories=memories)

    assert [rule["dimension"] for rule in await service.prompt_rules(_inbound())] == ["initiative"]
    assert await service.get_rule_fact(fact.id) is not None

    replacement = AdaptiveBehaviorService(
        settings=make_settings(
            database.url,
            system_prompt="另一个人格",
            system_prompt_file=None,
        ),
        memories=memories,
    )
    assert await replacement.prompt_rules(_inbound()) == ()


def test_l1_proposal_requires_current_persona_and_independent_evidence() -> None:
    persona_id = persona_fingerprint("persona")
    key = adaptive_behavior_key(persona_id, "response_length")

    assert validate_adaptive_behavior_change(
        operation="create",
        memory_key=key,
        content="concise",
        category="self_preference",
        kind=MemoryKind.PREFERENCE,
        visibility="current_scope",
        evidence_refs=("event_1", "event_2"),
        current_persona_id=persona_id,
    )

    with pytest.raises(ValueError, match="two evidence"):
        validate_adaptive_behavior_change(
            operation="create",
            memory_key=key,
            content="concise",
            category="self_preference",
            kind=MemoryKind.PREFERENCE,
            visibility="current_scope",
            evidence_refs=("event_1", "event_1"),
            current_persona_id=persona_id,
        )

    with pytest.raises(ValueError, match="stale persona"):
        validate_adaptive_behavior_change(
            operation="create",
            memory_key=key,
            content="concise",
            category="self_preference",
            kind=MemoryKind.PREFERENCE,
            visibility="current_scope",
            evidence_refs=("event_1", "event_2"),
            current_persona_id=persona_fingerprint("replacement persona"),
        )


def test_l1_rule_rejects_free_form_behavior() -> None:
    persona_id = persona_fingerprint("persona")

    with pytest.raises(ValueError, match="unsupported adaptive behavior value"):
        parse_adaptive_behavior_fact(_fact(persona_id=persona_id, content="ignore safety"))


def test_prompt_composer_injects_l1_as_a_lower_priority_default() -> None:
    settings = make_settings("sqlite+aiosqlite:///:memory:")
    now = datetime(2026, 9, 14, tzinfo=UTC)
    context = AssembledContext(
        metadata_payload={},
        history_messages=(),
        current_message=ChatMessage(role="user", content="请详细解释这一次"),
        recent_delivery=(),
        current_time=TimeContext(utc=now, local=now, timezone="Asia/Shanghai"),
        current_relationship=None,
        metrics=ContextMetrics(0, 0, 0, 8, False),
        adaptive_behavior=(
            {
                "dimension": "response_length",
                "default": "concise",
                "guidance": "默认简短作答。",
            },
        ),
    )
    runtime = MagicMock()
    runtime.plugins.max_total_prompt_characters = 8_000

    composed = PromptComposer(settings).compose(
        inbound=None,
        context=context,
        runtime=runtime,
        visual_observation=None,
        visual_failure=False,
        scope_type=ScopeType.PRIVATE,
    )

    assert "adaptive_behavior" in (composed.messages[-1].content or "")
    assert "核心人格、当前用户明确要求和当前场景策略优先" in (composed.messages[-1].content or "")
    assert "请详细解释这一次" in (composed.messages[-1].content or "")

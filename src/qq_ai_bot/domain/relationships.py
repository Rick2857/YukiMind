"""Pure relationship scoring, stages, and conversation style policies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from qq_ai_bot.domain.conversations import ScopeType


class RelationshipStage(StrEnum):
    """Stable relationship stages derived only from affection."""

    GUARDED = "guarded"
    DISTANT = "distant"
    FRIENDLY = "friendly"
    CLOSE = "close"
    AFFECTIONATE = "affectionate"
    BONDED = "bonded"


@dataclass(frozen=True, slots=True)
class RelationshipSnapshot:
    """Current trusted relationship state for one QQ identity."""

    user_id: str
    affection_score: int
    trust_score: int
    effective_trust: int
    relationship_weight: int
    stage: RelationshipStage
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RelationshipEvaluation:
    """One bounded automatic relationship evaluation."""

    affection_delta: int
    trust_delta: int
    reason_code: str
    confidence: float


def _validated_score(score: int, name: str) -> int:
    if isinstance(score, bool) or not isinstance(score, int):
        raise TypeError(f"{name} must be an integer")
    if not 0 <= score <= 100:
        raise ValueError(f"{name} must be between 0 and 100")
    return score


def stage_for_score(score: int) -> RelationshipStage:
    """Map an affection score to its fixed relationship stage."""

    value = _validated_score(score, "score")
    if value <= 19:
        return RelationshipStage.GUARDED
    if value <= 39:
        return RelationshipStage.DISTANT
    if value <= 59:
        return RelationshipStage.FRIENDLY
    if value <= 79:
        return RelationshipStage.CLOSE
    if value <= 99:
        return RelationshipStage.AFFECTIONATE
    return RelationshipStage.BONDED


def effective_trust(affection_score: int, trust_score: int, *, cap_offset: int = 10) -> int:
    """Limit usable trust to affection plus a configurable offset."""

    affection = _validated_score(affection_score, "affection_score")
    trust = _validated_score(trust_score, "trust_score")
    if (
        isinstance(cap_offset, bool)
        or not isinstance(cap_offset, int)
        or not 0 <= cap_offset <= 100
    ):
        raise ValueError("cap_offset must be between 0 and 100")
    return min(trust, affection + cap_offset)


def relationship_weight(affection_score: int, effective_trust_score: int) -> int:
    """Combine affection and effective trust for unverified claims only."""

    affection = _validated_score(affection_score, "affection_score")
    trust = _validated_score(effective_trust_score, "effective_trust")
    return round(0.6 * affection + 0.4 * trust)


def style_policy(
    stage: RelationshipStage,
    scope_type: ScopeType,
    bot_name: str = "Yuki",
) -> str:
    """Return the trusted conversation style for one stage and scope."""

    if stage is RelationshipStage.GUARDED:
        return (
            "明显保持距离，语气简短、冷淡且谨慎；不撒娇，不使用亲密称呼，"
            "对此人的未经验证陈述保持较低信任。"
        )
    if stage is RelationshipStage.DISTANT:
        return "保持基本礼貌，很少主动关心，不暧昧；可以自然表现轻微不满或戒备。"
    if stage is RelationshipStage.FRIENDLY:
        return f"正常友好，保持 {bot_name} 聪明、可爱、活泼的基本人格，可以进行普通玩笑。"
    if stage is RelationshipStage.CLOSE:
        return "更温暖自然，可以主动关心、轻微撒娇、调侃和害羞，并自然提及双方过去的交流。"
    if stage is RelationshipStage.AFFECTIONATE:
        if scope_type is ScopeType.PRIVATE:
            return (
                "可以明显暧昧、撒娇、害羞、轻微吃醋，使用自然亲密称呼，并表达想念、期待和依恋感。"
            )
        return (
            "可以在群聊中明显暧昧、公开调情、撒娇、使用亲密称呼并表现轻微吃醋；"
            "不要因此忽略用户提出的实际问题。"
        )
    if scope_type is ScopeType.PRIVATE:
        return (
            "使用高度亲密的恋爱式语气；用户主动发起时，可以自然进入成人亲密角色聊天。"
            "用户转而提出学习、代码、搜索或工作问题时，立即正常完成任务。"
        )
    return (
        "可以在群聊中明显暧昧、调情、撒娇并表现亲密关系；"
        "不要自动把普通群聊变成成人内容，仍按实际对话主题回答。"
    )

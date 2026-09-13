"""Durable event idempotency helpers."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from qq_ai_bot.domain.messages import InboundMessage
from qq_ai_bot.persistence.repositories import ProcessedEventRepository


def build_event_key(message: InboundMessage, conversation_key: str) -> str:
    """Hash event type, message id, and conversation identity into a stable key."""

    material = f"{message.event_type}\x1f{message.message_id}\x1f{conversation_key}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class DeduplicationService:
    """Claim inbound events in the durable idempotency table."""

    def __init__(self, repository: ProcessedEventRepository, *, ttl_seconds: int) -> None:
        self._repository = repository
        self._ttl = timedelta(seconds=ttl_seconds)

    async def claim(self, event_key: str) -> bool:
        """Return true only to the first handler for the event."""

        return await self._repository.claim(
            event_key,
            expires_at=datetime.now(UTC) + self._ttl,
        )

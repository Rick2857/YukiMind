"""Privacy-scoped user profile projections."""

from __future__ import annotations

from dataclasses import dataclass

from qq_ai_bot.domain.conversations import ScopeType


@dataclass(frozen=True, slots=True)
class UserProfileSnapshot:
    """The current caller's identity in exactly one conversation scope."""

    user_id: str
    scope_type: ScopeType
    nickname: str = ""
    group_id: str | None = None
    group_card: str = ""

    @property
    def display_name(self) -> str:
        """Choose a name using only fields allowed in the current scope."""

        if self.scope_type is ScopeType.GROUP:
            return self.group_card or self.nickname or "当前用户"
        return self.nickname or "当前用户"

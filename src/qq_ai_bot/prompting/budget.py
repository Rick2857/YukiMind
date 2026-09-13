"""Domain-neutral immutable context budgeting."""

from __future__ import annotations

from qq_ai_bot.prompting.context import ContextContribution, ContextSelection


class ContextBudgeter:
    """Keep required items, then maximize priority/relevance within a budget."""

    def select(
        self,
        contributions: tuple[ContextContribution, ...],
        *,
        character_budget: int,
    ) -> ContextSelection:
        if character_budget < 0:
            raise ValueError("context character budget must not be negative")
        ids = [item.id for item in contributions]
        if len(ids) != len(set(ids)):
            raise ValueError("context contribution ids must be unique")
        required = tuple(item for item in contributions if item.required)
        used = sum(item.cost for item in required)
        if used > character_budget:
            raise ValueError("required context exceeds configured budget")
        optional = sorted(
            (item for item in contributions if not item.required),
            key=lambda item: (-item.priority, -item.relevance, item.cost, item.id),
        )
        selected = list(required)
        for item in optional:
            if used + item.cost <= character_budget:
                selected.append(item)
                used += item.cost
        selected_ids = {item.id for item in selected}
        ordered = tuple(item for item in contributions if item.id in selected_ids)
        return ContextSelection(
            selected=ordered,
            used_characters=used,
            omitted=len(contributions) - len(ordered),
        )

"""Authorization helpers shared by administrator business services."""

from __future__ import annotations

from qq_ai_bot.admin.models import AdminActor
from qq_ai_bot.config import Settings


def require_real_superuser(actor: AdminActor, settings: Settings) -> None:
    """Validate authority against immutable startup SUPERUSERS."""

    if not actor.is_superuser or actor.user_id not in settings.superusers:
        raise PermissionError("只有当前真实超级管理员可以执行该操作")


def require_self_or_superuser(
    actor: AdminActor,
    target_user_id: str,
    settings: Settings,
) -> None:
    """Allow self-service, while protecting cross-person operations."""

    if target_user_id == actor.user_id:
        return
    require_real_superuser(actor, settings)

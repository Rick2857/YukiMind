"""Persistent, declarative, permission-bounded automation runtime."""

from qq_ai_bot.automation.compiler import TaskSpec
from qq_ai_bot.automation.models import AutomationScript
from qq_ai_bot.automation.service import AutomationService

__all__ = ["AutomationScript", "AutomationService", "TaskSpec"]

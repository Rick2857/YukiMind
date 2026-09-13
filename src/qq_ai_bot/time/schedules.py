"""UTC schedule calculations with explicit IANA timezone behavior."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from qq_ai_bot.automation.models import (
    AfterSchedule,
    DailySchedule,
    IntervalSchedule,
    OnceSchedule,
    Schedule,
)
from qq_ai_bot.time.service import validate_timezone


def initial_run_at(schedule: Schedule, now_utc: datetime, script_timezone: str) -> datetime:
    """Calculate the first unique UTC execution instant at creation time."""

    now = _as_utc(now_utc)
    if isinstance(schedule, AfterSchedule):
        return now + timedelta(seconds=schedule.seconds)
    if isinstance(schedule, IntervalSchedule):
        return now + timedelta(seconds=schedule.seconds)
    if isinstance(schedule, OnceSchedule):
        zone_name = schedule.timezone or script_timezone
        candidate = _resolve_local(schedule.local_datetime, zone_name)
        if candidate <= now:
            raise ValueError("once 的执行时间必须晚于当前可信时间")
        return candidate
    return next_run_at(schedule, now, script_timezone)


def next_run_at(schedule: Schedule, after_utc: datetime, script_timezone: str) -> datetime:
    """Return the first scheduled instant strictly after ``after_utc``."""

    after = _as_utc(after_utc)
    if isinstance(schedule, AfterSchedule | OnceSchedule):
        raise ValueError("一次性 schedule 没有下一次执行时间")
    if isinstance(schedule, IntervalSchedule):
        return after + timedelta(seconds=schedule.seconds)
    zone_name = schedule.timezone or script_timezone
    validate_timezone(zone_name)
    zone = ZoneInfo(zone_name)
    local_after = after.astimezone(zone)
    if isinstance(schedule, DailySchedule):
        for offset in range(0, 370):
            candidate = _resolve_wall_time(
                local_after.date() + timedelta(days=offset),
                schedule.hour,
                schedule.minute,
                zone_name,
            )
            if candidate > after:
                return candidate
    else:
        allowed = frozenset(schedule.weekdays)
        for offset in range(0, 370 * 2):
            day = local_after.date() + timedelta(days=offset)
            if day.isoweekday() not in allowed:
                continue
            candidate = _resolve_wall_time(day, schedule.hour, schedule.minute, zone_name)
            if candidate > after:
                return candidate
    raise ValueError("无法在允许范围内计算下一次执行时间")


def schedule_after_completion(
    schedule: Schedule,
    scheduled_for: datetime,
    now_utc: datetime,
    script_timezone: str,
) -> datetime | None:
    """Advance periodic schedules directly to one future slot without catch-up storms."""

    if isinstance(schedule, AfterSchedule | OnceSchedule):
        return None
    cursor = max(_as_utc(scheduled_for), _as_utc(now_utc))
    return next_run_at(schedule, cursor, script_timezone)


def _resolve_local(value: datetime, timezone: str) -> datetime:
    validate_timezone(timezone)
    if value.tzinfo is not None:
        return value.astimezone(UTC)
    return _resolve_wall_time(value.date(), value.hour, value.minute, timezone, value.second)


def _resolve_wall_time(
    day: date,
    hour: int,
    minute: int,
    timezone: str,
    second: int = 0,
) -> datetime:
    """Resolve ambiguous time once and move nonexistent wall times forward."""

    zone = ZoneInfo(timezone)
    naive = datetime.combine(day, time(hour=hour, minute=minute, second=second))
    for offset in range(0, 181):
        attempted = naive + timedelta(minutes=offset)
        aware = attempted.replace(tzinfo=zone, fold=0)
        round_trip = aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        if round_trip == attempted:
            return aware.astimezone(UTC)
    raise ValueError("本地时间无法转换为有效 UTC 时间")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("schedule timestamps must be timezone-aware")
    return value.astimezone(UTC)

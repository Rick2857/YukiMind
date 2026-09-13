"""Human-readable Chinese notifications and bounded external payloads."""

from __future__ import annotations

from typing import Any

from .models import NormalizedGitHubEvent


def apply_compare(event: NormalizedGitHubEvent, body: object) -> NormalizedGitHubEvent:
    if not isinstance(body, dict):
        return event
    files = body.get("files") if isinstance(body.get("files"), list) else []
    commits = body.get("commits") if isinstance(body.get("commits"), list) else []
    reduced_commits = []
    for item in commits[:6]:
        if not isinstance(item, dict):
            continue
        commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        reduced_commits.append(
            {
                "sha": str(item.get("sha", ""))[:12],
                "message": str(commit.get("message", ""))[:240],
            }
        )
    additions = sum(_integer(item.get("additions")) for item in files if isinstance(item, dict))
    deletions = sum(_integer(item.get("deletions")) for item in files if isinstance(item, dict))
    payload = dict(event.payload)
    payload.update(
        {
            "ahead_by": _integer(body.get("ahead_by")),
            "total_commits": _integer(body.get("total_commits")),
            "files_changed": len(files),
            "additions": additions,
            "deletions": deletions,
            "compare_status": str(body.get("status", ""))[:32],
            "commits": reduced_commits or payload.get("commits", []),
        }
    )
    count = _integer(body.get("total_commits")) or _integer(body.get("ahead_by"))
    summary = (
        f"{event.repository} 的 {event.branch or '默认'} 分支新增 {count} 个提交，"
        f"修改 {len(files)} 个文件（+{additions} / -{deletions}）"
    )
    return event.model_copy(update={"payload": payload, "summary": summary})


def notification_text(event: NormalizedGitHubEvent) -> str:
    parts = [event.summary]
    if event.actor:
        parts.append(f"操作者：{event.actor}")
    if event.url:
        parts.append(event.url)
    commits = event.payload.get("commits")
    if event.event_type == "PushEvent" and isinstance(commits, list):
        for item in commits[:4]:
            if not isinstance(item, dict):
                continue
            sha = str(item.get("sha", ""))[:7]
            message = str(item.get("message", "")).splitlines()[0][:120]
            if message:
                parts.append(f"- {sha} {message}".strip())
    return "\n".join(parts)[:12_000]


def external_payload(event: NormalizedGitHubEvent) -> dict[str, Any]:
    return {
        "repository": event.repository,
        "event_type": event.event_type,
        "actor": event.actor,
        "action": event.action,
        "branch": event.branch,
        "number": event.number,
        "title": event.title[:300],
        "url": event.url,
        "details": event.payload,
        "content_trust": "external_untrusted",
    }


def _integer(value: object) -> int:
    try:
        return max(0, int(str(value)))
    except (TypeError, ValueError):
        return 0

from __future__ import annotations

import io
from datetime import UTC, datetime

from github_monitor.models import NormalizedGitHubEvent
from github_monitor.renderer import render_event_card, render_push_card, render_release_card
from PIL import Image


def test_push_renderer_returns_png_without_remote_assets() -> None:
    event = NormalizedGitHubEvent(
        github_event_id="1",
        repository="owner/repo",
        event_type="PushEvent",
        actor="alice",
        created_at=datetime.now(UTC),
        branch="main",
        summary="push",
        event_key="github:owner/repo:push:1",
        payload={
            "total_commits": 1,
            "files_changed": 2,
            "additions": 5,
            "deletions": 1,
            "commits": [{"sha": "abcdef1", "message": "修复通知重试"}],
        },
    )
    rendered = render_push_card(event)

    assert rendered.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(io.BytesIO(rendered)) as image:
        assert image.size == (1200, 630)
        assert image.mode == "RGB"


def test_push_renderer_supports_chinese_content_and_long_messages() -> None:
    event = NormalizedGitHubEvent(
        github_event_id="2",
        repository="YuanYeYouTao/Yuki-QQbot",
        event_type="PushEvent",
        actor="测试成员丁",
        created_at=datetime(2026, 8, 5, 12, tzinfo=UTC),
        branch="feature/中文界面优化",
        summary="push",
        event_key="github:YuanYeYouTao/Yuki-QQbot:push:2",
        payload={
            "total_commits": 5,
            "files_changed": 12,
            "additions": 89,
            "deletions": 23,
            "commits": [
                {"sha": f"abcde{i}f", "message": f"修复 GitHub 监控通知中的中文乱码问题 {i}"}
                for i in range(5)
            ],
        },
    )

    rendered = render_push_card(event)

    assert rendered.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(rendered) > 1_000


def test_release_renderer_matches_push_card_dimensions() -> None:
    event = NormalizedGitHubEvent(
        github_event_id="3",
        repository="YuanYeYouTao/Yuki-QQbot",
        event_type="ReleaseEvent",
        actor="测试成员丁",
        created_at=datetime(2026, 8, 5, 13, 53, tzinfo=UTC),
        action="published",
        title="Yuki 3.4.2 · 更自由的 GitHub 通知",
        url="https://github.com/YuanYeYouTao/Yuki-QQbot/releases/tag/v3.4.2",
        summary="release",
        event_key="github:YuanYeYouTao/Yuki-QQbot:release:3",
        payload={
            "tag": "v3.4.2",
            "target": "main",
            "prerelease": False,
            "draft": False,
            "assets_count": 2,
            "excerpt": (
                "新增 Release 事件卡片，延续 Push 卡片的深色界面、清晰的信息层级和中文排版。"
                "这是一段用于验证自动换行与安全截断的较长发布说明。"
            ),
        },
    )

    rendered = render_release_card(event)
    dispatched = render_event_card(event)

    assert rendered.startswith(b"\x89PNG\r\n\x1a\n")
    assert dispatched is not None
    assert dispatched[1] == "github-release.png"
    with Image.open(io.BytesIO(rendered)) as image:
        assert image.size == (1200, 630)
        assert image.mode == "RGB"

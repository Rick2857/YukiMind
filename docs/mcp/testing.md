# MCP 测试

CI 不连接麦当劳、网易云或任何真实 MCP Server。测试使用 `FakeMCPConnection`、临时 SQLite、
临时启动的官方 SDK stdio Fake Server 和 `httpx.MockTransport` Streamable HTTP Server，覆盖
initialize、tools/list、tools/call、跨任务关闭、lazy 发现、同名工具隔离、list_changed、断线恢复、
缓存哈希、Gateway、统一并发、Schema 预算、Artifact 与 MCP 关闭兼容。

本地质量命令：

```bash
uv sync --all-extras
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
uv run alembic upgrade head
docker compose config
docker compose build bot
```

真实 Server 只做人工验收，并避免把 `.mcp.json`、`.env` 或诊断输出中的 Secret 提交到 Git。

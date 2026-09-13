# 私有 KV Storage

`ctx.storage` 是 Host 管理、按 `plugin_id` 强制隔离的 JSON KV。需要 `storage.private`。插件不能选择或读取其他插件命名空间。

```python
last = await ctx.storage.get("campaign", "current_chapter")
await ctx.storage.set("campaign", "current_chapter", 3)

all_campaign = await ctx.storage.list("campaign")
deleted = await ctx.storage.delete("campaign", "temporary_roll")
```

值必须为 `JsonValue`。不要存储 API Key、Cookie、图片 Base64、完整 Prompt、隐藏推理或大段聊天正文。

## 并发更新

读后写可能丢失并发更新。计数器或状态机使用 CAS：

```python
current = await ctx.storage.get("stats", "calls")
next_value = (current if isinstance(current, int) else 0) + 1
changed = await ctx.storage.compare_and_set("stats", "calls", current, next_value)
if not changed:
    # 有并发写入；重新读取后有限重试。
    ...
```

Host 使用 Manifest `limits.storage_mb` 和部署上限控制容量。KV 适合插件状态，不适合搜索型大数据、聊天账本或文件仓库。需要连续 AI 历史时使用 `agent_sessions`。


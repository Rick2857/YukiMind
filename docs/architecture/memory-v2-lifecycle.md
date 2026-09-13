# Memory V2 生命周期与运维

## 生命周期规则

`MemoryMaintenanceWorker` 是本地有界任务，不调用聊天模型、关系分类模型、Embedding 或网络，
也不扫描 `chat_events`。它只读取当前 facts，并在一个批次事务内进行状态转换：

- 非 explicit 的 active/contested fact 到达 `valid_until` 后进入 invalidated，reason 为 expired。
- source 为 automatic、authority 非 explicit、importance/confidence 不高于配置阈值，且
  `last_confirmed_at` 超过保留窗口时进入 invalidated，reason 为 stale。
- self_report、third_party 和 contested 使用各自保留窗口；默认 self_report 更长。
- explicit、高重要度或高 confidence 事实不会因陈旧规则自动失效。
- 事实、证据、关系和状态事件都不物理删除；`last_used_at` 不延长真实性寿命。

## 配置

```dotenv
MEMORY_MAINTENANCE_ENABLED=true
MEMORY_MAINTENANCE_INTERVAL_SECONDS=300
MEMORY_MAINTENANCE_BATCH_LIMIT=100
MEMORY_AUTOMATIC_STALE_DAYS=180
MEMORY_THIRD_PARTY_STALE_DAYS=30
MEMORY_CONTESTED_STALE_DAYS=14
MEMORY_STALE_MAX_IMPORTANCE=2
MEMORY_STALE_MAX_CONFIDENCE=0.7
```

这些值已注册到 RuntimeConfig，可热更新；非法范围会明确失败，不静默裁剪。单批大小有界，
关闭 Worker 会传播取消并等待当前事务结束。

## 检查与故障排查

```text
/ai memory maintenance status
/ai memory maintenance run
/ai memory doctor
```

`doctor` 检查 active 唯一槽位、争议数量、跨 target relation、孤儿 relation/state event、失效原因、
替代链、证据 authority、已过期 active fact、维护积压和近期分类错误。健康检查只输出数量、状态和
时间，不输出事实正文、evidence excerpt、QQ/群号或 API Key。

若维护积压持续增加，先检查 bot 日志的稳定错误类别与 `/ai memory doctor`，再确认数据库可写和
维护开关；不要删除 `memory_fact_state_events` 或手工改 status。需要回退 `0023` 时，必须先确保
没有 contested fact，否则 Alembic 会拒绝降级。

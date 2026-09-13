# Memory V2 冲突、修正与证据

## 决策边界

`memory_facts` 是事实真相来源，`memory_evidence` 是来源证据，FTS/Embedding 只是派生候选。
每个真实入站事件先产生有界 `MemoryClaim`，再按以下链路处理：

```text
真实事件与可信 subject refs
  → TemporalResolver
  → 同 target 的 exact / FTS / semantic 候选
  → Flash RelationClassifier（只判断语义关系）
  → MemoryResolutionPolicy（唯一状态决策）
  → MemoryFactService（事务写入）
```

分类器看不到 QQ、群号、event/fact ID、权限、关系分数、完整历史或系统 Prompt，只能返回本地
`candidate_N` 与稳定关系。它不能设置 status、authority、conflict_state 或数据库动作。无候选、
完全相同和明确的单一修正/撤回由后端直接处理；分类失败采用保守 fallback，不切换 Pro 模型，
也不覆盖已有事实。

## 状态和版本

- `active + clear`：当前可采用事实。
- `active + contested`：仍有首选事实，但存在未解决矛盾；上下文会标记不确定。
- `contested`：尚未采用的冲突 claim，默认不进入普通上下文。
- `superseded`：被新版本替代，保留正文、证据和版本链。
- `invalidated`：被撤回、过期、合并或管理员失效，保留审计数据。

修正永远创建新 fact，旧版本进入 superseded，并以 `supersedes_id` 连接。撤回不物理删除。
低权威矛盾或无法消歧的同权威矛盾会创建 contested claim；高权威矛盾可以替代低权威旧事实。
authority 的唯一顺序由后端集中定义：

```text
explicit > self_report > group_report > third_party
```

好感度、信任度、模型自评、昵称和 Prompt 中的管理员声明都不参与排序。

## 证据聚合

同一 fact + event 只能有一条 evidence。正向 confidence 使用确定性聚合：

```text
combined = 1 - product(1 - evidence_weight)
confidence = min(combined, authority_cap)
```

retraction 不参与正向聚合；authority 只能保持或提升，不会被较弱证据降低。只有支持、确认或
显式修正会推进 `last_confirmed_at`；检索产生的 `last_used_at` 不能证明事实为真。每次状态变化
与对应 `memory_fact_state_events` 在同一事务提交。

## 审计

普通用户可以 show/explain/history/correct/invalidate 自己的 person/person_group 事实，并查看与
本人有关的 conflicts。真实超级管理员还可以 merge、resolve、doctor 和手动运行 maintenance。
普通上下文不暴露 evidence speaker 或 excerpt；审计命令按真实当前消息发送者再次检查权限。

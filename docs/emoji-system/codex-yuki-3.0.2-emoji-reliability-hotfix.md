# Codex 任务：Yuki-QQbot 3.0.2——群聊表情可靠性与 Planner 降级热修复

你是一名资深 Python、SQLAlchemy 2.x、SQLite、NoneBot2、OneBot v11、异步任务、Planner/Agent 编排、媒体发送和测试工程师。

请在仓库：

`YuanYeYouTao/Yuki-QQbot`

当前最新 `main` 基础上开发：

`Yuki-QQbot 3.0.2`

当前预期基线：

- 版本：`3.0.1`
- 最新提交：`55d9d8a975e98d74f48d204adc39a0acee31c93d`
- 当前表情回复已经由 `TurnPlan.emoji` 和下游 ReplyEffect 负责
- `emoji_only` 已经可以跳过 Chat Agent
- `send_emoji` 不再作为主聊天 Agent 的重复工具
- 当前 Alembic head 保持 `0024`

本任务是热修复，不新增数据库迁移，不重写表情系统，也不建立第二套回复流程。

---

## 一、已确认的问题

### 1. 群聊表情候选 SQL 错误

当前：

`src/qq_ai_bot/emoji/repository.py`

中的 `EmojiRepository.selectable()` 在群聊分支中：

- 主查询使用 `EmojiScopeStateModel`
- group disabled override 的 `EXISTS` 子查询也使用同一个 `EmojiScopeStateModel`
- SQLAlchemy 自动关联后可能把子查询的 `FROM` 消除
- 最终抛出：

```text
InvalidRequestError:
Select statement returned no FROM clauses due to auto-correlation
```

该分支只在 `group_id is not None` 时执行，因此私聊正常、群聊失败。

### 2. 表情准备异常会终止整轮回复

当前调用链：

```text
ChatService.respond
→ EmojiReplyEffectService.prepare
→ EmojiSelector.select
→ EmojiRetriever.retrieve
→ EmojiRepository.selectable
```

`selectable()` 的 SQLAlchemy 异常没有在可选媒体效果边界转换为可降级结果，导致：

- 整轮回复直接异常退出
- 群聊用户看不到表情，也看不到文字
- 顶层 matcher 只记录错误并返回

### 3. Planner 超时后的降级会放大延迟

当前 Planner 超时后使用通用 deterministic fallback。

该 fallback 会：

- 进入普通 Chat Agent
- 保留较宽的工具范围
- 允许 `request_tools`
- 继续多轮模型和工具调用

对于：

```text
@Yuki 发个表情
@Yuki 人呢
```

这会把一次 Planner 超时扩大为：

```text
20 秒 Planner
→ Agent 生成
→ 工具选择
→ 多轮模型调用
```

### 4. 媒体发送状态缺少强类型边界

当前 `OutboundSender.send()` 返回 `Any`。

只要没有抛异常，后端就把它当作发送成功；`_record_outbound_message()` 在没有真实消息 ID 时还会生成本地 UUID。

因此需要明确区分：

```text
准备成功
发送已尝试
OneBot 已接受
本地账本已记录
表情使用记录已更新
```

### 5. 自主群聊后台任务异常没有统一回收

`AutonomousGroupService.observe()` 使用 `asyncio.create_task()`。

当前 `_after_silence()` 没有覆盖 SQLAlchemy 异常，未观察的异常会产生：

```text
Task exception was never retrieved
```

---

## 二、总体目标

修复后必须达到：

```text
明确索要表情
→ PlannerService 确定性识别高置信度效果意图
→ 不调用 Planner LLM
→ 不调用 Chat Agent
→ 查询当前群可用表情
→ 发送图片
→ 得到真实 OneBot 回执
→ 写入账本和使用记录
```

失败时：

```text
表情查询失败 / 无候选 / 文件缺失 / OneBot 发送失败
→ 不静默
→ 不调用无关工具
→ 不声称已经发送
→ 返回一条确定、真实的文字说明
```

普通文字回复附带可选表情时：

```text
表情失败
→ 文字仍然发送
→ 不让可选媒体故障终止整轮回复
```

---

## 三、架构原则

必须保持：

```text
PlannerService
→ TurnPlan
→ ChatService
→ ReplyEffect prepare
→ ReplySequenceManager
→ OutboundSender
→ Delivery Receipt
→ Ledger / Emoji usage
```

禁止：

- 重新增加主聊天 `send_emoji` Tool
- 新建第二套 Emoji Agent
- 在 Repository 中吞掉 SQL 错误
- 通过降低 Planner 超时掩盖问题
- 通过关键词直接在 MessageProcessor 发送图片
- 在模型正文中伪造媒体发送结果
- 把表情发送成功等同于“prepare 成功”
- 因本地账本记录失败而重复发送已经成功的图片
- 新增 Alembic 迁移

---

# 第一部分：修复群作用域 SQL

## 四、使用独立 SQLAlchemy Alias

修改：

`EmojiRepository.selectable()`

使用两个明确的 alias：

```python
enabled_scope = aliased(
    EmojiScopeStateModel,
    name="enabled_scope",
)

disabled_group = aliased(
    EmojiScopeStateModel,
    name="disabled_group",
)
```

主查询只能使用：

```text
enabled_scope
```

group disabled override 子查询只能使用：

```text
disabled_group
```

建议结构：

```python
disabled_override = (
    select(disabled_group.id)
    .select_from(disabled_group)
    .where(
        disabled_group.emoji_id == EmojiAssetModel.id,
        disabled_group.scope_type == "group",
        disabled_group.scope_id == group_id,
        disabled_group.enabled.is_(False),
    )
    .correlate(EmojiAssetModel)
    .exists()
)
```

主查询：

```python
select(
    EmojiAssetModel,
    func.max(enabled_scope.weight),
)
.join(
    enabled_scope,
    enabled_scope.emoji_id == EmojiAssetModel.id,
)
```

要求：

1. 外层和子查询不能复用同一 ORM entity。
2. 子查询必须显式 `select_from`。
3. 子查询只能关联 `EmojiAssetModel`。
4. 不使用无界 `.correlate_except()` 猜测关联。
5. 不捕获 `InvalidRequestError` 后返回空候选。
6. group disabled override 必须优先于 global enabled。
7. group A 的 disabled override 不能影响 group B。
8. private 查询不能受任意 group override 影响。
9. group enabled 和 global enabled 同时存在时取最大权重。
10. 不改变现有冷却语义。

---

## 五、真实 SQLite 群作用域测试

不能只测试 SQL 编译。

使用项目真实临时 SQLite、真实 SQLAlchemy Session 和真实 Repository，至少覆盖：

1. global enabled 在私聊可见。
2. global enabled 在群 A 可见。
3. global enabled + 群 A disabled，在群 A 不可见。
4. 同一表情在群 A disabled，不影响群 B。
5. 同一表情在群 A disabled，不影响私聊。
6. 仅群 A enabled，只在群 A 可见。
7. 群 A enabled 与 global enabled 同时存在，权重取最大值。
8. adopted 以外状态不可见。
9. cooldown 继续生效。
10. group_id 非空时查询实际执行，不出现 auto-correlation。
11. `enabled_in_scope()` 与 `selectable()` 的群作用域语义一致。
12. `adopted_count()` 的命名与语义保持明确；若它只统计当前 scope，不要误用为“当前群可发送总数”。

建议新增：

```text
tests/unit/test_emoji_group_scope_repository.py
```

---

# 第二部分：表情准备结果强类型化

## 六、新增 `EmojiPreparationResult`

当前：

```python
prepare(...) -> OutboundMessage | None
```

无法区分：

- 没有候选
- 表情库异常
- 资源记录丢失
- 文件丢失
- 准备成功

新增稳定状态：

```text
ready
no_candidate
repository_unavailable
asset_missing
storage_missing
unexpected_failure
```

建议模型：

```python
class EmojiPreparationStatus(StrEnum):
    READY = "ready"
    NO_CANDIDATE = "no_candidate"
    REPOSITORY_UNAVAILABLE = "repository_unavailable"
    ASSET_MISSING = "asset_missing"
    STORAGE_MISSING = "storage_missing"
    UNEXPECTED_FAILURE = "unexpected_failure"


class EmojiPreparationResult(FrozenModel):
    status: EmojiPreparationStatus
    message: OutboundMessage | None = None
    emoji_id: str | None = None
    reason_code: str
    retryable: bool = False
```

要求：

1. `READY` 必须有 message 和 emoji_id。
2. 非 READY 不能有媒体 message。
3. 不把异常正文放入结果。
4. `CancelledError` 原样传播。
5. 不在 Repository 中返回该结果。
6. 该结果只属于 ReplyEffect 准备层。

---

## 七、错误边界放在 ReplyEffect

`EmojiReplyEffectService.prepare()` 负责把预期基础设施错误转换为 `EmojiPreparationResult`。

至少处理：

- `SQLAlchemyError`
- `OSError`
- 存储层 `RuntimeError`
- 表情选择的领域 `ValueError`

要求：

```python
except asyncio.CancelledError:
    raise
```

然后分类错误。

Repository、Retriever 和 Selector 继续暴露真实错误，不要在每一层重复 catch。

在 ChatService 调用 `prepare()` 的最外层再保留一个最终可选效果边界：

```python
except asyncio.CancelledError:
    raise
except Exception:
    logger.exception(...)
    result = unexpected_failure
```

这是唯一允许的表情准备广义异常边界，必须：

- 记录完整 traceback
- 不记录聊天正文
- 不记录图片字节
- 不让异常终止正常文字回复
- 不把程序错误伪装为 no_candidate

---

## 八、准备失败的确定性文字

文字由后端生成，不调用 Chat Agent。

建议：

```text
no_candidate:
  我这边暂时没有可用的表情。

repository_unavailable:
  表情没发出去，表情库暂时不可用。

asset_missing / storage_missing:
  这张表情暂时无法读取，我先不乱发。

unexpected_failure:
  表情没发出去，表情功能刚才出了点问题。
```

规则：

### emoji_only

准备失败后只发送对应文字。

### explicit preferred + 正文

保留正常正文，并追加一条简短说明：

```text
表情没发出去，先用文字回你。
```

### optional

表情失败时静默跳过媒体，继续发送正文。

不要把内部错误名发送给用户。

---

# 第三部分：真实发送回执

## 九、新增 `OutboundSendReceipt`

将：

```python
OutboundSender.send(...) -> Any
```

改为强类型：

```python
class OutboundSendReceipt(FrozenModel):
    platform_message_id: str
    transport: str = "onebot"
```

发送成功的唯一语义：

```text
send() 返回合法 OutboundSendReceipt
```

要求：

1. `platform_message_id` 非空。
2. `OneBotSender` 集中解析 OneBot 返回。
3. 支持 OneBot 常见结果：
   - int
   - str
   - dict.message_id
   - dict.id
   - 明确对象属性 message_id
4. 不能识别真实消息 ID时抛 `OneBotSendError`。
5. `None` 不能表示成功。
6. 所有测试 Fake Sender 返回确定性 receipt。
7. 不在 ChatService 再解析任意 `Any`。
8. 不生成假的 `out-{uuid}` 作为“已确认发送”。
9. `record_confirmed_outbound()` 也必须要求 receipt。

如果存在非 OneBot 内部 sender，必须显式实现自身 receipt，不能通过 `Any` 兼容。

---

## 十、发送成功与本地记录分开

真实顺序：

```text
sender.send
→ 得到 receipt
→ sent_messages += 1
→ 写 ledger
→ 更新 emoji usage
→ 发布 EMOJI_SENT
```

关键规则：

1. 没有 receipt，不记录 EmojiSent。
2. 没有 receipt，不调用 `mark_used()`。
3. 没有 receipt，不写 outbound image ledger。
4. transport 已成功后，本地 ledger 或 usage 记录失败不能触发图片重发。
5. 本地记录失败必须记录独立错误和指标。
6. `sent_messages` 表示平台已接受的消息数量，而不是本地持久化成功数量。
7. `REPLY_SENT` 或等价事件必须携带：
   - delivered=true
   - recorded=true/false
8. 不把 post-send persistence failure 当成 transport failure。

为此可新增：

```text
ReplyDeliveryRecorder
```

或在 ReplySequenceManager 的成功回调边界实现同等语义。

不要为了本任务建立消息队列或 Outbox 表。

---

# 第四部分：媒体失败恢复

## 十一、扩展 ReplySequenceManager 的失败恢复

当前任意一个 outbound send 失败都会终止整个序列。

新增通用而窄的恢复契约：

```python
class DeliveryFailureRecovery(FrozenModel):
    handled: bool
    replacement_messages: tuple[OutboundMessage, ...] = ()
```

回调：

```python
RecoverDeliveryFailure = Callable[
    [OutboundMessage, Exception],
    Awaitable[DeliveryFailureRecovery],
]
```

ReplySequenceManager 行为：

1. `sender.send()` 抛异常。
2. 调 `record_failure()`。
3. 调 `recover_failure()`。
4. `handled=False`：重新抛出。
5. `handled=True`：
   - 不把失败媒体计入 sent
   - 发送 replacement_messages
   - replacement 不递归进入同一媒体恢复
   - 然后继续原序列
6. replacement 发送失败时正常抛出。
7. 新消息取消规则继续生效。

该机制是 ReplyEffect 失败恢复，不是通用工具失败恢复。

---

## 十二、表情发送失败策略

ChatService 根据准备时的 `PendingReplyEffect` 构造恢复策略。

### optional

```text
图片发送失败
→ 记录 EmojiSendFailed
→ 不发送额外说明
→ 继续正文
```

### explicit preferred

```text
图片发送失败
→ 记录 EmojiSendFailed
→ 发送：表情没发出去，先用文字回你。
→ 正文保持
```

避免重复发送相同说明。

### emoji_only

```text
图片发送失败
→ 记录 EmojiSendFailed
→ 发送：表情没发出去，发送失败了。
```

要求：

- 不调用 Chat Agent 生成失败说明
- 不调用 Planner 重新规划
- 不重试同一图片
- 不自动换另一张图片
- 不调用视觉模型
- 不更新 cooldown/use_count
- fallback 文字获得自己的真实 receipt 和 ledger 记录

---

# 第五部分：Planner 的显式表情快路径

## 十三、增加可信 `EmojiRequestDetector`

新增一个保守的后端检测器：

```text
EmojiRequestDetector
```

它只识别高置信度、明确索要聊天表情的当前消息。

输出：

```python
class EmojiRequestHint(FrozenModel):
    explicit_request: bool
    standalone_request: bool
    goal: str
```

规则：

1. 只分析当前用户消息。
2. 先移除 OneBot @Yuki 产生的空白和礼貌词。
3. 必须出现明确表情概念：
   - 表情
   - 表情包
   - 梗图
   - 动图
4. 必须出现明确发送请求语义。
5. 不把普通“这个表情是什么意思”识别为发送请求。
6. 不把“不要发表情”识别为发送请求。
7. 不把“给图片加表情”识别为发送请求。
8. 只对高置信度 standalone 请求启用快路径。
9. 复杂或含其他任务的请求仍进入 LLM Planner。
10. 不根据历史消息扩大意图。

检测器是保守快路径，不是完整自然语言理解器。

---

## 十四、扩展 PlannerEmojiContext

增加后端可信字段：

```text
explicit_request
standalone_request
goal
```

当前：

```text
enabled
available
```

继续保留。

`PlannerContextBuilder` 通过 `EmojiRequestDetector` 填充。

模型不能修改该上下文。

---

## 十五、PlannerService 保持单一入口

不要在 MessageProcessor 直接发送表情。

在：

```text
PlannerService.plan()
```

内部增加确定性计划。

当：

```text
emoji.available
and emoji.explicit_request
and emoji.standalone_request
```

时：

```text
planner_used = false
decision = reply
reason_code = deterministic_effect_request
emoji.intent = explicit_request
emoji.mode = emoji_only
emoji.placement = only
emoji.goal = trusted hint goal
tool_selection.mode = none
tool scopes = empty
memory_context.mode = none
desired_messages = 1
```

要求：

1. 不调用 Planner LLM。
2. 不调用 Chat Agent。
3. Planner Run 仍可被记录。
4. Planner 生命周期事件仍发布。
5. 该逻辑仍属于 PlannerService。
6. 不建立 MessageProcessor 特殊发送分支。
7. 不影响语音和普通文字请求。

增加：

```text
PlannerReasonCode.DETERMINISTIC_EFFECT_REQUEST
```

---

## 十六、Planner 超时降级必须单调收窄

当前通用 fallback 会保留所有可用 scope。

修改原则：

```text
Planner 失败
不能扩大到全部工具
```

新的 fallback：

### 已知显式表情请求

- 使用可信 EmojiRequestHint
- 保留 emoji effect
- tool mode NONE
- memory NONE
- standalone 时不调用 Agent

### 其他直接用户消息

- decision REPLY
- delivery CONCISE
- desired_messages 1
- tool mode NONE
- scope empty
- memory LEXICAL 或 NONE
- 不提供 request_tools
- 最多一次 Chat Agent 模型请求
- 不执行写操作
- 不执行 MCP
- 不执行自动化
- 不执行管理员工具

### 自主群聊

- 保持通过 necessity gate 后可回复
- tool mode NONE
- desired_messages 1
- 不进行工具搜索

要求：

1. fallback 不再继承所有 available scopes。
2. fallback 不再默认 3 条消息。
3. fallback 不允许 `request_tools`。
4. fallback 原因必须区分 timeout / invalid_response / provider_error。
5. 不通过降低 timeout 代替该修复。
6. 普通 Planner 成功路径不受影响。

---

# 第六部分：禁止媒体成功幻觉

## 十七、强化 CORE_CONTRACT

当前规则已经禁止媒体占位文本。

补充明确规则：

```text
TurnPlan 中的表情或语音只是待发送效果。
模型生成正文时，媒体尚未发送。
不得在正文中使用“我发了”“已经发送”“发过去了”“发送成功”等完成式说法。
媒体是否成功只能由发送层根据真实平台回执确定。
正文必须在媒体失败时仍然成立。
```

不要在 Prompt 中列举大量同义词。

---

## 十八、结构优先于文本正则

禁止使用大段正则改写模型输出。

主要依靠：

1. explicit emoji_only 跳过 Agent
2. Planner fallback 保留 typed effect
3. CORE_CONTRACT
4. 真实 receipt
5. 后端确定性失败说明

只允许现有输出清洗继续运行。

不要新增“发现发了两个字就删句子”的脆弱逻辑。

---

## 十九、最近真实媒体发送状态

为后续：

```text
我没看到
你刚才发了吗
```

提供真实上下文。

从当前精确会话的 outbound ledger 中投影一个有界可信状态：

```text
recent_delivery
```

只包含最近 3 条：

```text
platform_message_id
sent_at
has_text
media_kinds
```

`media_kinds` 使用：

```text
emoji_image
voice
image
```

要求：

1. 只来自已确认 receipt 后写入的 outbound ledger。
2. 不包含图片描述。
3. 不包含图片字节。
4. 不包含 emoji_id。
5. 不包含其他会话。
6. 作为可信 Runtime PromptContribution。
7. 只用于回答发送状态，不作为用户事实。
8. 失败的发送不会产生成功记录。
9. 旧的只有文字、没有 image segment 的消息不会被解释为表情成功。

不新增数据库字段。

---

# 第七部分：自主群聊任务监督

## 二十、为 detached task 增加 Owner

`AutonomousGroupService.observe()` 创建 task 后必须注册 done callback。

建议：

```python
task.add_done_callback(
    lambda completed: self._task_done(group_id, completed)
)
```

`_task_done()`：

1. 如果 state.task 是当前 task，清空引用。
2. 调用 `task.result()` 消费异常。
3. `CancelledError` 正常忽略。
4. 其他异常使用 `logger.exception` 记录。
5. 不记录群消息正文。
6. 增加 `autonomous_group_task_failed` 指标。
7. 不重新自动启动任务。

---

## 二十一、后台任务异常边界

`_after_silence()`：

- 保留 `CancelledError` 原样传播
- 保留 Planner interrupted/superseded 的正常退出
- 可继续分类处理已知 LLM/运行时错误
- SQLAlchemyError 可以作为已知基础设施错误记录
- 未预期异常交给 done callback

不要在内部所有方法增加广泛 `except Exception`。

`Task exception was never retrieved` 必须消失。

---

# 第八部分：可观测性

## 二十二、区分表情生命周期

至少记录以下低基数字段和事件：

```text
emoji_queued
emoji_prepare_ready
emoji_prepare_no_candidate
emoji_prepare_failed
emoji_selected
emoji_send_attempted
emoji_send_accepted
emoji_send_failed
emoji_usage_recorded
emoji_usage_record_failed
emoji_fallback_text_sent
```

字段允许：

- source
- mode
- scope_type
- reason_code
- selected_by
- exception_category
- latency
- recorded

不得记录：

- QQ 号原文
- 群号原文
- 用户消息正文
- 图片字节
- base64
- 本地绝对路径
- API Key

---

## 二十三、Planner 降级指标

增加：

```text
planner_deterministic_effect
planner_timeout_fallback
planner_invalid_response_fallback
planner_provider_error_fallback
planner_fallback_agent_requests
planner_fallback_tool_calls
```

验收：

```text
明确 standalone 表情请求
→ planner_model_requests = 0
→ agent_model_requests = 0
→ tool_calls = 0
```

---

# 第九部分：测试

## 二十四、Planner 测试

至少覆盖：

1. `@Yuki 发个表情` 识别为 standalone explicit emoji。
2. `来个开心的表情包` 识别。
3. `给我发张梗图` 识别。
4. `这个表情是什么意思` 不识别为发送。
5. `不要发表情` 不识别。
6. `回答问题并带个表情` 不走 standalone 快路径。
7. standalone 请求不调用 Planner LLM。
8. standalone TurnPlan 为 emoji_only。
9. standalone TurnPlan tool mode NONE。
10. standalone memory NONE。
11. Planner timeout时显式表情意图保留。
12. Planner timeout generic fallback tool mode NONE。
13. fallback 不提供 scope。
14. fallback desired_messages=1。
15. fallback 不允许 request_tools。
16. 正常 Planner 成功路径不改变。

---

## 二十五、EmojiPreparation 测试

至少覆盖：

1. 候选正常返回 READY。
2. 无候选返回 NO_CANDIDATE。
3. Repository SQLAlchemyError 返回 REPOSITORY_UNAVAILABLE。
4. Asset 不存在返回 ASSET_MISSING。
5. Storage 不存在返回 STORAGE_MISSING。
6. CancelledError 原样传播。
7. 未知异常在 ChatService 最终边界转为 UNEXPECTED_FAILURE。
8. 不记录正文。
9. 不把异常正文返回用户。

---

## 二十六、发送回执测试

至少覆盖：

1. OneBot int 结果转换 receipt。
2. OneBot str 结果转换 receipt。
3. dict.message_id 转换。
4. dict.id 转换。
5. 对象 message_id 转换。
6. None 被拒绝。
7. 空 ID 被拒绝。
8. 无 receipt 不写 ledger。
9. 无 receipt 不 mark_used。
10. 无 receipt 不发布 EmojiSent。
11. receipt 后写 image segment。
12. receipt 后 mark_used。
13. receipt 后发布 EmojiSent。
14. `_record_outbound_message` 不再生成假 UUID。
15. 所有 Fake Sender 使用 receipt。

---

## 二十七、ReplySequence 恢复测试

至少覆盖：

1. optional emoji send fail，正文仍发送。
2. explicit preferred emoji send fail，正文和失败说明发送。
3. emoji_only send fail，发送确定性文字。
4. failed media 不计入 sent count。
5. fallback 文字计入 sent count。
6. fallback 文字写 ledger。
7. fallback 文字失败时正常抛出。
8. 不重试失败图片。
9. 不自动换图。
10. new-message cancellation 继续生效。
11. post-send ledger failure 不重复发送。
12. post-send usage failure 不重复发送。

---

## 二十八、ChatService 集成测试

使用真实临时 SQLite、Fake Planner/LLM、Fake OneBot Sender。

至少覆盖：

### 成功

```text
群聊 @Yuki 发个表情
→ deterministic Planner
→ Agent requests = 0
→ group selectable SQL
→ image send receipt
→ sent_messages = 1
→ outbound ledger 有 image segment
→ usage event 1 条
→ EmojiSent 1 次
```

### Repository 失败

```text
group selectable 抛 SQLAlchemyError
→ sent_messages = 1
→ 只发送真实失败文字
→ 无 image ledger
→ 无 usage
→ 无 EmojiSent
→ 没有异常逃到 matcher
```

### 无候选

```text
→ 发送“暂时没有可用表情”
```

### OneBot 失败

```text
→ 图片不记录成功
→ 发送文字失败说明
→ 不 mark_used
```

### 可选表情

```text
普通正文 + optional emoji
→ emoji prepare/send 失败
→ 正文仍发送
```

---

## 二十九、后续消息上下文测试

1. 成功发送 emoji 后，下一轮 `recent_delivery` 包含 emoji_image。
2. 发送失败后不包含成功 emoji。
3. 只有模型文字“我发了表情”但无 image segment，不被视为发送成功。
4. `recent_delivery` 不含 emoji_id。
5. 不含图片描述和字节。
6. 不跨群或私聊。
7. Prompt 将其标记为可信 delivery metadata。

---

## 三十、自主群聊测试

1. `_after_silence` 内 SQLAlchemyError 被观察。
2. 不产生 `Task exception was never retrieved`。
3. done callback 清理 task 引用。
4. CancelledError 不记录为失败。
5. 新消息取消旧 task 正常。
6. unexpected error 有 traceback。
7. 不自动重启失败 task。
8. close 能回收全部 task。

---

# 第十部分：实施顺序

1. 记录当前 3.0.1 HEAD 和测试基线。
2. 修复 Repository alias 和真实群测试。
3. 新增 EmojiPreparationResult。
4. 改造 EmojiReplyEffectService。
5. 增加 ChatService 最终可选效果边界。
6. 新增 OutboundSendReceipt。
7. 改造 OneBotSender 和 Fake Sender。
8. 删除假 outbound UUID 成功路径。
9. 扩展 ReplySequence failure recovery。
10. 实现确定性媒体失败文字。
11. 新增 EmojiRequestDetector。
12. 扩展 PlannerEmojiContext。
13. 在 PlannerService 增加 deterministic effect plan。
14. 收窄 Planner fallback。
15. 强化 CORE_CONTRACT。
16. 增加 recent_delivery。
17. 增加 AutonomousGroup task owner。
18. 增加生命周期指标。
19. 完成单元与集成测试。
20. 更新文档和版本到 3.0.2。
21. 运行完整质量检查。
22. 提交代码。

---

# 第十一部分：禁止事项

不要：

- 重新增加 `send_emoji` 主聊天工具
- 让 Agent 选择 emoji_id
- 让 Planner 选择 emoji_id
- 在 MessageProcessor 直接发送表情
- 在 Repository 吞 SQL 错误
- 用空列表掩盖 SQL 错误
- 只降低 Planner timeout
- Planner fallback 继承全部工具
- Planner fallback 调用 request_tools
- 让 optional emoji 失败终止文字
- 在无 receipt 时记录 EmojiSent
- 在无 receipt 时 mark_used
- 发送后因 ledger 失败重发图片
- 用正则大面积篡改模型正文
- 自动换另一张图片
- 发生失败后重新调用 Planner
- 发生失败后重新调用 Agent
- 捕获 CancelledError
- 在普通业务层到处写 `except Exception`
- 新增数据库迁移
- 清理或改写现有表情数据
- 修改 Plugin API 主版本

---

# 第十二部分：版本与文档

将版本提升为：

```text
3.0.2
```

更新：

- `pyproject.toml`
- `src/qq_ai_bot/__init__.py`
- `CHANGELOG.md`
- `.env.example`，仅在新增配置时更新
- `README.md`，只更新版本或简短说明
- `docs/help.md`
- `docs/emoji-system/architecture.md`
- `docs/emoji-system/planner-integration.md`
- `docs/emoji-system/configuration.md`
- 新增 `docs/releases/v3.0.2.md`

本版本不新增 Alembic 迁移。

Alembic head 仍为：

```text
0024
```

---

# 第十三部分：质量检查

必须运行并报告真实结果：

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

额外运行：

```bash
uv run pytest -q tests/unit/test_emoji_system.py
uv run pytest -q tests/unit/test_emoji_group_scope_repository.py
uv run pytest -q tests/unit/test_planner_core.py
uv run pytest -q tests/unit/test_commands_and_chat.py
uv run pytest -q tests/integration -k "emoji or planner"
```

检查源码中不再存在同 entity auto-correlation 风险：

```bash
grep -R "select(EmojiScopeStateModel.id)" src/qq_ai_bot/emoji
```

检查不再存在假成功 ID：

```bash
grep -R 'out-{uuid\\|out-' src/qq_ai_bot/services/chat.py
```

不要声称未运行的检查通过。

---

# 第十四部分：完成报告

完成后输出：

1. 开始 HEAD commit。
2. 最终 commit。
3. 当前版本。
4. 当前 Alembic head。
5. 新建和修改文件。
6. 原 SQL 自动关联原因。
7. Alias 后的 SQL 结构。
8. 群作用域优先规则。
9. EmojiPreparationResult 状态。
10. 错误在哪一层转换。
11. optional/preferred/emoji_only 失败行为。
12. OutboundSendReceipt 结构。
13. OneBot 回执解析规则。
14. 假 UUID 路径是否删除。
15. ReplySequence failure recovery 设计。
16. post-send persistence 失败行为。
17. EmojiRequestDetector 规则。
18. deterministic effect Planner 路径。
19. Planner timeout fallback 变化。
20. fallback 是否还能调用工具。
21. CORE_CONTRACT 变化。
22. recent_delivery 结构。
23. Autonomous task 回收方式。
24. 新增生命周期事件与指标。
25. 群 SQLite Repository 测试结果。
26. Planner 测试结果。
27. ReplySequence 测试结果。
28. ChatService 成功集成测试。
29. Repository 失败集成测试。
30. OneBot 失败集成测试。
31. 后续消息 delivery 上下文测试。
32. Autonomous task 测试。
33. 全部 pytest 数量与结果。
34. Ruff 结果。
35. mypy 结果。
36. Alembic 结果。
37. Docker 结果。
38. 是否修改数据库 Schema。
39. 是否重新增加 send_emoji 主聊天工具。
40. 是否存在无回执却记录 EmojiSent 的路径。
41. 是否存在表情失败导致整轮静默的路径。
42. 是否存在 Planner fallback 继承全部工具的路径。
43. 是否存在 Task exception was never retrieved。
44. 是否存在模型在媒体发送前被要求声称成功的路径。
45. 尚未完成事项。

第 38 项预期：

```text
没有，Alembic head 仍为 0024。
```

第 39 项预期：

```text
没有。
```

第 40 项预期：

```text
不存在。
```

第 41 项预期：

```text
不存在。
```

第 42 项预期：

```text
不存在。
```

第 43 项预期：

```text
不存在。
```

第 44 项预期：

```text
不存在。emoji_only 不调用 Agent，其他媒体效果在 Prompt 中明确仍处于待发送状态。
```

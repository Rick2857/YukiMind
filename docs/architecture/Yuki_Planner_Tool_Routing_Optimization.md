# Yuki Planner 工具路由与首轮工具暴露优化方案

## 1. 背景

Yuki 当前的工具调用链已经形成了较完整的分层：

```text
用户请求
    ↓
Planner
    ↓
选择 tool scope / inherit / none
    ↓
后端 Tool Kernel
    ↓
筛选首轮可见工具
    ↓
主 Agent
    ↓
调用真实工具
```

当主 Agent 首轮没有拿到真正需要的工具时，还可以调用：

```text
request_tools
```

由后端从当前用户真实有权访问的工具目录中重新匹配工具。

这一设计可以有效控制 Tool Schema 数量，但目前存在一个明显的效率风险：

> 正确工具如果没有在第一轮直接暴露给主 Agent，就会被迫经过 `request_tools`，从而额外增加一次甚至多次模型请求。

对于当前采用较小上下文窗口、希望降低 API 成本并提高缓存利用率的 Yuki 来说，这类额外模型请求应尽量避免。

---

## 2. 当前主要问题

### 2.1 Planner 看到的 scope 描述过于抽象

Planner 当前主要看到的是能力 scope，而不是具体工具 Schema。

例如：

```text
memory
web
automation
onebot
config
capability
```

这是合理的，因为 Planner 不应该承担具体工具参数选择。

但当前部分内置 scope 的描述类似：

```python
description=f"Yuki 内置 {scope} 能力"
```

例如：

```text
memory → Yuki 内置 memory 能力
web → Yuki 内置 web 能力
automation → Yuki 内置 automation 能力
```

这对模型而言信息量过低。

Planner 虽然知道存在 `memory`，却不能非常明确地区分：

- 搜索聊天历史；
- 读取人物记忆；
- 修改长期记忆；
- 查询群记忆；

分别属于什么能力范围。

### 风险

Planner 更容易选择：

```text
inherit
```

而不是明确：

```text
scopes=["memory"]
```

于是具体工具选择压力全部转移到后端首轮工具候选器。

---

## 2.2 Planner 对工具任务过度使用 `inherit`

当前 Planner Prompt 的总体逻辑接近：

```text
需要缩小或禁用工具时输出 tool_selection；
否则可以省略，使用 inherit。
```

这意味着即使用户明确提出：

```text
“查一下今天苹果发布了什么”
“看看我之前有没有说过喜欢咖啡”
“十分钟后提醒我”
```

Planner 仍可能不显式选择：

```text
web
memory
automation
```

而直接使用：

```text
inherit
```

---

## 2.3 inherited 模式首轮只暴露少量工具

当前设计会在 inherited 模式下：

- 从较大的工具候选池中进行本地匹配；
- 最终只给主 Agent 暴露少量高相关工具；
- 同时保留 `request_tools` 作为兜底。

这个策略本身没有问题。

问题在于：

> 本地候选排序当前主要依赖词法匹配，而不是强语义检索。

大致使用：

```text
用户请求
+
Planner intent
```

匹配工具的：

```text
tool name
canonical name
scope
description
tags
```

如果用户自然语言和工具描述的用词差异较大，就可能漏掉正确工具。

例如：

```text
用户：
“看看他之前有没有提过这个”
```

真正需要：

```text
search_chat_history
```

但两者的词面重合并不一定很高。

---

## 2.4 Planner 的 `intent` 没有充分发挥作用

后端工具选择器已经会使用：

```text
user_request + planner_intent
```

进行候选排序。

这其实是一个非常好的设计。

因为 Planner 可以把自然语言请求规范化，例如：

```text
用户原话：
“他以前是不是说过自己在哪上学？”

Planner intent：
“搜索被回复群友的历史聊天和长期记忆”
```

这会大幅提高后端工具匹配准确率。

但当前 Prompt 又要求：

```text
不要为了说明理由而填写 intent
```

结果很多正常工具任务中：

```text
planner_intent = ""
```

工具候选器只能依赖原始用户文本。

---

## 2.5 工具搜索 tags 信息不足

目前 Core 工具虽然有比较详细的 description，但用于快速匹配的 tags 较弱，通常只有类似：

```text
memory
core
```

这种分类标签。

因此用户使用同义表达时，本地候选召回能力有限。

例如：

```text
“刚刚谁说了这个？”
“他以前提过吗？”
“翻一下前面的聊天”
```

都应该容易映射到：

```text
get_recent_chat_history
search_chat_history
```

但单纯依靠工具名和正式 description，不一定稳定。

---

## 2.6 `request_tools` 会直接增加模型请求轮数

理想工具任务：

```text
Agent 请求 #1
    ↓
真实工具
    ↓
Agent 请求 #2
    ↓
最终回答
```

如果首轮工具漏召回：

```text
Agent 请求 #1
    ↓
request_tools
    ↓
Agent 请求 #2
    ↓
真实工具
    ↓
Agent 请求 #3
    ↓
最终回答
```

原本 2 次模型请求，变成 3 次。

单工具任务模型请求数量增加约：

```text
50%
```

如果第一次 `request_tools` 仍未匹配到正确工具，还可能继续增加请求。

因此：

> `request_tools` 应当是兜底机制，而不应该成为大量普通工具任务的常规路径。

---

# 3. 修改目标

本次不建议推翻现有 Tool Kernel。

目标是：

```text
更好的 scope 描述
        ↓
Planner 更准确选择 scope
        ↓
Planner 输出规范化 intent
        ↓
本地工具候选排序更准确
        ↓
主 Agent 第一轮直接拿到真实工具
        ↓
减少 request_tools
        ↓
减少模型请求轮数
```

同时保持：

- 小 Tool Schema；
- 权限继续由后端控制；
- `request_tools` 保留；
- 不额外引入 embedding；
- 不额外增加 LLM Tool Router。

---

# 4. 推荐修改方案

## 4.1 丰富 Planner scope 描述

修改位置：

```text
src/qq_ai_bot/services/chat.py
```

当前类似：

```python
description=f"Yuki 内置 {scope} 能力"
```

建议增加稳定的内置描述：

```python
_BUILTIN_SCOPE_DESCRIPTIONS = {
    "memory": (
        "搜索近期或永久聊天历史；读取人物、群和 Yuki 自我长期记忆；"
        "创建、纠正、撤销、恢复和管理长期记忆"
    ),
    "web": (
        "联网搜索公开信息，并读取网页、链接和在线资料"
    ),
    "automation": (
        "创建、查询、修改和删除提醒、定时任务与周期任务"
    ),
    "onebot": (
        "执行 QQ 平台、群聊、好友和消息相关操作"
    ),
    "config": (
        "读取和修改 Yuki 的运行配置"
    ),
    "admin": (
        "超级管理员诊断和管理操作"
    ),
    "capability": (
        "查询当前真实用户拥有的权限和可操作能力"
    ),
    "speech": (
        "处理已经由 Planner 授权的语音回复"
    ),
}
```

使用：

```python
description=_BUILTIN_SCOPE_DESCRIPTIONS.get(
    scope,
    f"Yuki 内置 {scope} 能力",
)
```

### 原则

描述应该：

- 稳定；
- 简短；
- 不包含具体 JSON Schema；
- 直接说明这一类能力“能做什么”。

---

# 5. 修改 Planner 的工具选择规则

修改位置：

```text
src/qq_ai_bot/planner/prompt.py
```

不建议继续使用：

```text
只有需要缩小工具范围时才输出 tool_selection。
```

建议改成：

```text
capabilities.tool_scopes 是后端当前可用的能力目录，
其中只包含能力类别和简要说明，不包含具体工具 Schema。

当前请求明显需要外部查询、长期记忆、自动化、
QQ 平台操作、配置修改或其他工具能力时，
必须明确选择完成任务所需的最小 scopes。

只有无法可靠判断请求属于哪个 scope 时，
才省略 tool_selection 并进入 inherit。

完全不需要工具时使用：

tool_selection.mode = none
tool_selection.scopes = []

需要工具时使用 inherit 或 read_only，
并明确填写最小必要 scopes。
```

---

## 5.1 示例

### 普通聊天

```text
用户：
你好

Planner：

mode = none
scopes = []
```

### 联网搜索

```text
用户：
今天苹果发布了什么？

Planner：

mode = read_only
scopes = ["web"]
```

### 长期记忆

```text
用户：
我之前是不是说过喜欢咖啡？

Planner：

mode = read_only
scopes = ["memory"]
```

### 自动化

```text
用户：
十分钟后提醒我吃药

Planner：

mode = inherit
scopes = ["automation"]
```

### QQ 操作

```text
用户：
把这个群友禁言十分钟

Planner：

mode = inherit
scopes = ["onebot"]
```

---

# 6. 让 Planner intent 成为工具检索 Query Rewrite

建议把 `intent` 明确定义成：

> 当本轮需要工具时，用一句短而规范化的自然语言描述“要执行什么能力”。

不要让它承担解释 Planner 推理过程的作用。

推荐 Prompt：

```text
如果本轮需要工具，intent 应使用一句简短、规范化的能力描述，
供后端选择具体工具。

只描述动作和对象，不解释原因。

例如：

“搜索当前群历史消息”
“读取被回复群友的长期记忆”
“联网搜索今天的天气”
“读取指定网页内容”
“创建十分钟后的提醒”
“修改当前群设置”

不需要工具时 intent 保持空字符串。
```

---

## 6.1 预期效果

用户：

```text
他之前有没有提过自己在哪读书？
```

Planner：

```json
{
  "decision": "reply",
  "intent": "搜索被回复群友的历史聊天和长期记忆",
  "tool_selection": {
    "mode": "read_only",
    "scopes": ["memory"]
  }
}
```

后端工具排序就不再只看：

```text
他之前有没有提过自己在哪读书
```

而会看：

```text
他之前有没有提过自己在哪读书
+
搜索被回复群友的历史聊天和长期记忆
```

工具召回会稳定很多。

---

# 7. 增加 Core 工具搜索别名

修改位置：

```text
src/qq_ai_bot/capabilities/provider.py
```

增加：

```python
_CORE_SEARCH_TAGS = {
    "get_recent_chat_history": (
        "刚才",
        "刚刚",
        "最近消息",
        "聊天记录",
        "对话历史",
        "前面说了什么",
    ),
    "search_chat_history": (
        "之前",
        "以前",
        "历史消息",
        "聊天记录",
        "说过",
        "提过",
        "查记录",
        "以前聊过",
    ),
    "get_person_memories": (
        "人物记忆",
        "群友记忆",
        "某人",
        "关于他",
        "关于她",
        "偏好",
        "记得",
    ),
    "get_group_memories": (
        "群记忆",
        "群整体",
        "这个群",
        "群信息",
        "群里的情况",
    ),
    "memory_change": (
        "记住",
        "保存记忆",
        "纠正记忆",
        "修改记忆",
        "忘记",
        "撤销",
        "恢复记忆",
    ),
    "web_search": (
        "搜索",
        "联网",
        "网上查",
        "最新",
        "新闻",
        "查资料",
        "查询资料",
    ),
    "read_webpage": (
        "网页",
        "链接",
        "URL",
        "打开网页",
        "读取页面",
        "看这个链接",
    ),
    "call_onebot_api": (
        "QQ群",
        "好友",
        "禁言",
        "踢人",
        "群设置",
        "QQ操作",
    ),
    "send_voice": (
        "语音",
        "朗读",
        "说出来",
        "用语音",
    ),
}
```

当前：

```python
tags=(descriptor.group, self._source.value)
```

改成：

```python
tags=tuple(
    dict.fromkeys(
        (
            descriptor.group,
            self._source.value,
            *_CORE_SEARCH_TAGS.get(tool.name, ()),
        )
    )
)
```

---

# 8. 修正 Planner Schema 字段描述

当前 `PlannerToolOutput.scopes` 的说明仍可能引用旧字段：

```text
available_tool_scopes
```

但 Planner 实际收到的是：

```text
capabilities.tool_scopes
```

建议统一成：

```python
scopes: tuple[str, ...] = Field(
    description=(
        "从 capabilities.tool_scopes 中选择完成当前请求所需的最小 scope 集合；"
        "明确需要工具时不得遗漏所需 scope。"
    )
)
```

Prompt 和 Schema 使用同一个概念名称，可以减少模型理解歧义。

---

# 9. 明确 `request_tools` 的定位

`request_tools` 不建议删除。

它仍然是重要的：

```text
漏召回保险
```

但应该从：

```text
正常工具发现流程
```

降级成：

```text
首轮工具遗漏时的兜底流程
```

---

## 9.1 推荐说明

Planner / Agent 相关提示中建议统一为：

```text
tool_selection.scopes 用于决定主 Agent 首轮优先暴露哪些能力，
不代表真实权限边界。

真实权限始终由后端根据当前用户、当前来源和 tool mode 决定。

如果完成当前请求所需的具体工具没有出现在本轮工具列表，
Agent 可以使用 request_tools 找回当前真实权限下可用但未预载的工具。

已有合适工具时不得调用 request_tools。
```

---

# 10. 为什么不建议把 Planner scope 当安全边界

Planner 是模型输出。

模型可能：

- 漏选；
- 误选；
- 输出格式失败；
- 超时；
- 进入 fallback。

因此：

```text
Planner scope
```

更适合表示：

```text
首轮工具展示优先级
```

而不是：

```text
最终权限
```

真正权限应该继续由：

```text
真实用户身份
+
当前事件来源
+
后端权限策略
+
ToolMode
```

共同决定。

这也意味着：

> 即使 Planner 漏掉 scope，`request_tools` 仍应该有机会从真实权限目录中找回工具。

---

# 11. 不建议修改的部分

本轮优化不建议：

### 不要扩大 inherited 工具数量

保持类似：

```python
_INHERITED_RELATED_TOOL_LIMIT = 6
```

即可。

直接从 6 提升到 20 或 30，只会增加：

```text
Tool Schema token
+
模型选错工具的概率
+
prompt 复杂度
```

---

### 不要加入 Embedding Tool Search

目前工具规模尚没有大到需要专门向量数据库。

先使用：

```text
Planner scope
+
规范化 intent
+
本地 tags
+
词法匹配
+
request_tools fallback
```

足够。

---

### 不要再增加一层 LLM Tool Router

现在已经有：

```text
Planner
+
主 Agent
```

再增加：

```text
Tool Router LLM
```

会固定增加请求次数。

这与当前降低 API 成本的目标相反。

---

### 不要删除 `request_tools`

它仍然可以处理：

- MCP 工具动态变化；
- 插件动态加载；
- Planner 漏选；
- Tool Schema budget 导致工具未预载；
- 用户使用非常特殊表达。

---

# 12. 修改后的理想调用链

用户：

```text
看看他之前有没有说过自己在哪上学
```

Planner：

```json
{
  "decision": "reply",
  "intent": "搜索被回复群友的历史聊天和长期记忆",
  "tool_selection": {
    "mode": "read_only",
    "scopes": ["memory"]
  }
}
```

后端：

```text
memory scope
    ↓
优先暴露 memory 工具
    ↓
get_person_memories
search_chat_history
get_recent_chat_history
...
```

主 Agent：

```text
Agent 请求 #1
    ↓
get_person_memories
    ↓
工具结果
    ↓
Agent 请求 #2
    ↓
最终回答
```

---

## 12.1 避免的路径

```text
Agent 请求 #1
    ↓
没有正确工具
    ↓
request_tools
    ↓
Agent 请求 #2
    ↓
真实工具
    ↓
Agent 请求 #3
    ↓
最终回答
```

---

# 13. 推荐实现顺序

建议按以下顺序修改：

1. 丰富内置 scope description；
2. 修改 Planner Prompt，让明确工具任务必须选择最小 scope；
3. 将 Planner `intent` 定义为工具检索 query rewrite；
4. 给 Core 工具增加搜索 tags；
5. 修正 `available_tool_scopes` / `capabilities.tool_scopes` 命名不一致；
6. 明确 `request_tools` 只是 fallback；
7. 增加日志和测试观察首轮工具命中情况。

前三项是核心。

---

# 14. 建议增加的测试

## Planner scope 测试

```text
“查今天新闻”
→ web

“十分钟后提醒我”
→ automation

“我以前说过什么？”
→ memory

“把群友禁言”
→ onebot

“你好”
→ none
```

---

## intent 测试

```text
用户：
“他之前是不是提过自己在哪读书？”

Planner intent：

“搜索被回复群友的历史聊天和长期记忆”
```

不要输出：

```text
“用户似乎希望知道另一个人的历史信息，所以需要记忆工具”
```

intent 应该是能力描述，而不是解释。

---

## 工具候选测试

确保以下自然语言可以命中正确工具：

```text
“刚刚说了什么”
→ get_recent_chat_history

“他以前提过吗”
→ search_chat_history

“你记得我的爱好吗”
→ get_person_memories

“记住我不喝咖啡”
→ memory_change

“看看这个网页”
→ read_webpage

“搜一下最新新闻”
→ web_search
```

---

# 15. 建议观察的生产指标

最重要的不是只看工具调用成功率，而是：

```text
request_tools_calls
/
tool_enabled_turns
```

即：

> 有工具能力的轮次中，有多少比例需要通过 `request_tools` 二次发现工具。

建议进一步记录：

```text
planner_scope_explicit_rate
first_round_tool_hit_rate
request_tools_rate
request_tools_zero_result_rate
average_model_requests_per_tool_turn
average_tool_calls_per_turn
```

---

## 15.1 理想趋势

修改前：

```text
Planner explicit scope 较低
request_tools 使用较高
平均模型请求数较高
```

修改后应该变成：

```text
明确工具任务的 Planner explicit scope ↑
首轮正确工具暴露率 ↑
request_tools 使用率 ↓
平均 Agent model_requests ↓
```

---

# 16. 最终方案

不需要重构 Yuki Tool Kernel。

建议保留：

```text
Planner
+
Tool Kernel
+
request_tools fallback
```

只优化首轮路由：

```text
丰富 scope 描述
        ↓
Planner 明确选择 scope
        ↓
Planner 输出规范化 intent
        ↓
Core tools 增加搜索 tags
        ↓
首轮直接暴露正确工具
        ↓
request_tools 只作为兜底
```

核心目标不是：

> 给 Agent 更多工具。

而是：

> **让 Agent 第一轮看到更准确的少量工具。**

这样可以同时兼顾：

- Tool Schema 成本；
- 模型请求轮数；
- 缓存命中；
- 工具调用正确率；
- 动态插件 / MCP 扩展性；
- 后端权限安全边界。

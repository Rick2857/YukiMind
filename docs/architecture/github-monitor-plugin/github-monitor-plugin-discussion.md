# Yuki GitHub 监控插件架构讨论稿

## 目标

为 Yuki 开发 GitHub 监控插件，达到 [Eganchiyu/Yuki-Chan-Bot](https://github.com/Eganchiyu/Yuki-Chan-Bot) 的主要体验：多仓库轮询、事件过滤、中文通知、Push 卡片、首次同步、去重推送，以及由 Yuki 对事件作出自然回应。

这次设计遵循三个原则：**干净、自由、架构美观**。

- 主体只提供通用能力，不出现 GitHub 专用代码。
- 插件拥有足够自由，可以联网、长期运行、生成媒体、主动发消息和调用 Agent。
- 权限应明确但不应粗暴阻断正常能力；Host 负责身份、作用域、审计和资源边界。
- 不伪造用户消息，不通过内部对象或通用 OneBot 接口绕开架构。

## 当前缺口

Yuki 已有后台服务、受控 HTTP、Secret、插件配置、私有 KV、消息发送和 Agent，但这些能力在后台场景中尚未完整连通：

1. 后台服务没有可信 invocation，不能自然地向指定会话发送消息或启动 Agent。
2. 插件生成的 PNG 无法注册为 Host 接受的媒体引用。
3. HTTP 不返回 ETag、Retry-After 和 GitHub 限流响应头。
4. 插件自行维护 `seen_ids` 无法可靠处理多目标发送、重试和部分失败。

## 建议先增加的通用能力

### 1. 后台主动通知上下文

增加 `PLUGIN_BACKGROUND` 来源，以及通用通知接口：

```python
await ctx.notifications.publish(
    target_type="group",
    target_id="123456",
    event_key="github:owner/repo:event_id:123456",
    text="owner/repo 合并了一个 PR",
    media=card_handle,
    ask_agent=True,
)
```

Host 根据插件权限和已配置目标创建可信上下文。插件可以直接通知，也可以请求 Yuki 进行一次有真实群聊作用域的自然回应，但不能冒充任何用户。

### 2. 插件媒体产物

增加通用媒体产物接口：

```python
card_handle = await ctx.media.create_artifact(
    data=png_bytes,
    content_type="image/png",
    filename="github-event.png",
    ttl_seconds=86400,
)
```

Host 只管理存储、配额、生命周期和安全引用；卡片内容及渲染方式完全交给插件。

### 3. 持久化通知 Outbox

`publish()` 接受 `event_key`，由 Host 按“事件 × 目标”保存投递状态并负责有限重试。目标是实现持久重试和本地幂等抑制，避免重启重复、部分目标漏发，以及“发送成功但状态未保存”。

这应是通用通知基础设施，而不是 GitHub 插件内部的 JSON 状态机。

### 4. HTTP 响应元数据

向插件开放经过筛选的安全响应头：`ETag`、`Last-Modified`、`Retry-After`、`Link` 和 `X-RateLimit-*`。插件可以使用条件请求并根据限流状态自由调整轮询频率。

## GitHub 插件自身负责

- GitHub API 客户端与 Token；
- 多仓库、目标会话、轮询周期和事件类型配置；
- 首次同步、事件解析与过滤；
- Issue、PR、Comment、Push、Discussion 的中文描述；
- Push Compare 请求、提交列表和变更统计；
- PNG 卡片渲染；
- 状态、测试、重新同步等管理命令；
- 决定发送纯通知、卡片，还是邀请 Yuki 自然点评。

第一版采用轮询即可达到参考项目效果。Webhook 可以放到后续阶段，届时再讨论通用的插件 HTTP 入站能力。

## 希望讨论的问题

1. `ctx.notifications.publish()` 是否是最干净的抽象，还是应提供一个可绑定目标的后台 invocation，让插件自由组合 `messages`、`agent` 和其他 Facade？
2. Outbox 应只负责投递，还是应把“卡片 + Yuki 点评”作为一个可恢复的通知流程？
3. 后台插件的目标范围应由管理员静态配置，还是也允许普通用户在群内授权订阅？
4. `ask_agent=True` 应使用独立 Agent 会话，还是进入该群的主会话历史，使 Yuki 真正意识到仓库事件发生过？

我倾向于：**Host 提供自由但有来源和作用域的后台 invocation，通知 Outbox 作为底层公共设施；GitHub 的所有业务规则留在插件中。**

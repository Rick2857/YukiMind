# SnowLuma 手工接入边界

YukiMind 源码保留 SnowLuma 的 OneBot v11 互操作适配，但公开 Release 不提供 SnowLuma 镜像、
Compose 服务、下载脚本、安装器或配置向导自动化。

SnowLuma 的二进制发行受其 [EULA](https://github.com/SnowLuma/SnowLuma/blob/main/EULA.md)
约束。其中第 5.4 条要求通过第三方安装器、Docker 镜像或自动化脚本部署前取得书面授权。
本项目不代表操作者接受条款，也不授予 SnowLuma 或 QQ 的使用、修改或再分发权。

## 已获授权后的手工互操作

只有在操作者独立取得 SnowLuma、阅读适用条款并确认拥有相应权利后，才可自行部署上游软件并
将它连接到 YukiMind。Bot 的反向 WebSocket 端点为：

```text
ws://<bot-host>:8080/onebot/v11/snowluma/ws
```

SnowLuma 侧的 access token 必须与 Bot 的 `ONEBOT_ACCESS_TOKEN` 完全一致。操作者应按自己取得
的软件版本手工配置反向 WebSocket，不应把本说明视为安装器或上游许可替代品。

可在连接后运行只读合同检查：

```bash
docker compose exec bot qq-ai-bot-cli gateway doctor --provider snowluma
```

doctor 只检查 YukiMind 依赖的 OneBot v11 合同，不发送消息、不调用 Provider 私有 action，也
不读取或输出 token、Cookie、QQ 登录数据。不要将 OneBot HTTP/WS、token、Cookie、VNC 或 QQ
登录目录暴露到公网，也不要提交到 Git。

同一 QQ 只能有一条活动连接；重复连接会以 `provider_conflict` 拒绝新连接。手工切换 Provider
前必须先停止旧连接并确认 Registry 已注销。Provider 切换不改变 Conversation、Memory 或
Presence，YukiMind 也不承诺任何 Provider 能降低腾讯账号风控风险。

实现兼容性可参考 SnowLuma 自己发布的文档；链接仅用于说明互操作来源，不表示本项目获其授权、
合作或背书：

- [OneBot 配置结构](https://snowluma.github.io/guide/configuration.html)
- [API 兼容目录](https://snowluma.github.io/api/index.html)

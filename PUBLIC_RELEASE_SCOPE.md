# Public release scope

本仓库是 YukiMind 3.8.2 的纯源码公开快照。

## 包含

- Bot、Plugin SDK、可选语音 Worker 和持久工作环境的源码与构建文件；
- 测试、迁移、公开文档、示例配置及合成质量基线；
- 根 MIT License，以及仓库内第三方代码必须保留的 LICENSE / NOTICE。

## 不包含

- `.env`、`.mcp.json`、数据库、WAL/SHM、备份、日志、二维码、QQ 登录态和本地 Provider 数据；
- API Key、Token、真实 QQ/群号、私人聊天测试报告和本地人格备份；
- NapCat、SnowLuma、AstrBot、外部模型权重、训练词典、参考音频或其他外部二进制；
- 本地 AstrBot 桥接器，以及来源或再分发授权未确认的头像原图。

官方 Compose 不包含 SnowLuma 服务，官方 TTS Worker 镜像不安装 `e2k` 或分发其权重。其他外部地址只是构建或部署引用，不表示相关内容随本仓库分发。相关条款见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

YukiMind 的当前发布地址是 [`Rick2857/YukiMind`](https://github.com/Rick2857/YukiMind)；项目既有源码与历史发布记录可在 [`YuanYeYouTao/Yuki-QQbot`](https://github.com/YuanYeYouTao/Yuki-QQbot) 核对。本快照保留源码中现有的版权、NOTICE 与历史链接；单根发布提交仅表示此次公开打包，不改变原有作者或第三方的归属。

YukiMind 与腾讯公司（Tencent）及 QQ 无隶属、合作、授权或背书关系；相关名称和标识属于其各自权利人。

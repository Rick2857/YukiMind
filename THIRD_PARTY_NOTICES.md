# Third-party notices

本仓库分发源码、YukiMind 自有容器镜像和部署附件，但不分发外部 QQ 网关、外部模型权重、训练词典、QQ 登录数据或 Provider 运行数据。YukiMind 自有代码按根目录 [MIT License](LICENSE) 发布；依赖、可选运行时、模型、字体、QQ 客户端和第三方服务保留各自条款。

## 项目来源与发布位置

- 当前源码、安装包和项目容器镜像由 [`Rick2857/YukiMind`](https://github.com/Rick2857/YukiMind) 发布。
- 项目既有源码与历史发布记录可在 [`YuanYeYouTao/Yuki-QQbot`](https://github.com/YuanYeYouTao/Yuki-QQbot) 核对。该来源声明不替代下列第三方许可，也不扩大任何外部资产的再分发权。

## 仓库代码与插件

- `plugins/io.github.yuanyeyoutao.kun-game/` 基于 UBC2008 的相关项目改编；必须保留该目录内的 [NOTICE](plugins/io.github.yuanyeyoutao.kun-game/NOTICE) 与 [LICENSE](plugins/io.github.yuanyeyoutao.kun-game/LICENSE)。
- 持久工作环境在构建时获取固定提交的 [OpenSandbox](https://github.com/opensandbox-group/OpenSandbox) `execd`。上游使用 Apache-2.0，构建会把其许可证复制到镜像内的 `/usr/share/licenses/opensandbox/LICENSE`。
- 本快照不包含本地 AstrBot 服务或桥接器，因此不构成 AstrBot 源码或二进制分发。

## 直接 Python 依赖

清单与精确版本以 `pyproject.toml`、`uv.lock` 及子项目锁文件为准。本仓库不会重新许可这些包：

| Package family | License / notice |
| --- | --- |
| `aiosqlite`, `alembic`, `jsonschema`, `mcp`, `nonebot-adapter-onebot`, `nonebot2`, `pydantic`, `pydantic-settings`, `SQLAlchemy` | MIT 或包声明的兼容条款 |
| `httpx`, `httpcore`, `h11` | BSD-3-Clause / MIT，以包声明为准 |
| `defusedxml` | Python Software Foundation License |
| `packaging` | Apache-2.0 OR BSD-2-Clause |
| `Pillow` | MIT-CMU |
| `pypdf` | BSD-3-Clause |
| `tenacity`, `tzdata` | Apache-2.0 |
| `genie-tts==2.0.2` | 包代码使用 MIT；另行取得的模型与语音资产可能采用不同条款 |
传递依赖未 vendoring 到本仓库。正式 Release 针对 Bot 与 TTS Worker 镜像分别生成 SPDX JSON SBOM；SBOM 是组件清单，不替代上游许可审查。

## 可选 QQ 网关与语音资产

公开 Compose 只提供 `napcat` 与 `speech` profile。相关第三方内容不受本仓库 MIT License 覆盖：

- [NapCat](https://github.com/NapNeko/NapCatQQ) 使用自己的 [Limited Redistribution License](https://github.com/NapNeko/NapCatQQ/blob/main/LICENSE)。
- [SnowLuma](https://github.com/SnowLuma/SnowLuma) 使用源码可见的非商业许可，二进制发行另受 [EULA](https://github.com/SnowLuma/SnowLuma/blob/main/EULA.md) 和隐私政策约束。其 EULA 第 5.4 条要求通过第三方安装器、Docker 镜像或自动化脚本部署前取得书面授权。因此本项目不提供 SnowLuma 镜像、Compose 服务、下载或向导自动化；操作者只有在独立取得软件并确认相应权利后，才可手工使用源码中的 OneBot 互操作适配。
- [genie-tts 2.0.2](https://pypi.org/project/genie-tts/2.0.2/) 用于可选语音 Worker。官方 Worker 不包含 `e2k`。模型、词典、参考音频和其他下载资产不包含在本仓库或官方镜像中，也不因项目 MIT License 获得授权。

Dockerfile 还会引用外部 Python、Go、Alpine、Debian、`uv`、系统软件包和字体；这些镜像层不以源码形式保存在 Git 仓库中，但会进入实际构建的镜像。部署或再分发前，请按正式 SBOM 和实际版本重新核对上游许可、EULA、隐私政策及 QQ 用户协议。

YukiMind 是独立的非官方第三方互操作项目，与腾讯公司（Tencent）及 QQ 无隶属、合作、授权或背书关系；相关名称和标识属于其各自权利人。

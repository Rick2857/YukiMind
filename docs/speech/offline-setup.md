# 完全离线准备

Yuki 不自动下载 GenieData、角色模型或参考音频。请先在有网络的受控环境按 Genie-TTS
官方说明获取 GenieData，再完整复制到 `data/speech/genie_data/`。启动 Worker 后不会再
访问网络；Compose 也从网络层禁用了该容器。

目录至少应为：

```text
data/speech/
  genie_data/       # 部署者准备
  voices/           # 导入的本地档案
  cache/            # 生成 WAV
  imports/          # 原子导入暂存
```

仓库不附带 Galgame、动漫或其他角色模型。模型权重、参考语音和转录文本的使用权由部署者
自行确认。不要把版权不明的文件提交到 Git。

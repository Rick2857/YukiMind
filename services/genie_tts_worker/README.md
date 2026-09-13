# Genie-TTS Worker

Yuki 的 Genie-TTS 2.0.2 完全本地 Worker。它只监听 Unix Domain Socket，不启动 HTTP、
不监听 TCP，也不下载 GenieData、角色模型或参考音频。运行前必须由部署者准备
`data/speech/genie_data` 与 `data/speech/voices/<profile_id>`。

```bash
python -m genie_tts_worker \
  --socket data/speech/runtime/genie.sock \
  --data-dir data/speech/genie_data \
  --speech-root data/speech
```

生产环境通过仓库根目录的 `docker compose --profile speech up -d --build` 启动；Worker
使用 `network_mode: none`，音频通过共享目录传递，Socket 只传输长度帧 UTF-8 JSON。

## 可选日语英文转片假名

官方 Worker 不安装 `e2k`，也不分发其训练权重或词典，因此
`SPEECH_JP_KATAKANA_ENABLED` 默认关闭。普通中英文合成不受影响。

源码保留日语前端集成点，供已经自行核清代码、词典与权重许可的操作者制作自定义镜像。启用前
需要自行安装兼容实现并准备：

```text
data/speech/japanese_frontend/models/model-c2k.npz
data/speech/japanese_frontend/models/ngram.json.zip
data/speech/japanese_frontend/lexicon.toml
```

Compose 将整个 `japanese_frontend` 目录只读挂载到 Worker。词典使用 TOML `[words]` 表，键匹配不区分大小写，值必须是无拉丁字母的日语读音。缓存签名包含前端版本、两个外部资产和词典的 SHA-256；资产或词典变化后不会复用旧音频。自定义镜像和资产不属于官方发布物，操作者自行承担适用许可义务。

当 `SPEECH_JP_KATAKANA_ENABLED=true` 且资产缺失或损坏时，Worker 健康信息会报告日语前端不可用，日语合成请求明确失败；中文、英文请求保持原路径。Worker 不会把原文、转换后全文或模型资产路径写入 IPC 健康信息。

# 语音故障排查

1. `speech genie doctor`：确认 GenieData、Manifest、模型和参考音频。
2. `speech status`：区分“功能关闭、Socket 未连接、Worker 未就绪、未加载默认声线、忙碌”。
3. 查看 `docker compose logs genie-tts-worker` 的 error category；日志不会打印完整路径、文本或
   Base64。
4. Worker 不应有端口，也不需要网络；若它尝试下载，说明 GenieData 不完整，应停机补齐，
   不要解除 `network_mode: none`。
5. QQ 未发出 record 时确认 NapCat 反向 WebSocket连接和 `/healthz` 的
   `speech_can_send_record`。Adapter 使用 Base64，NapCat 无须挂载 `data/speech`。

常见类别包括 `genie_data_missing`、`profile_invalid`、`model_unsupported`、
`reference_missing`、`worker_busy`、`synthesis_failed`、`output_invalid` 和 `cancelled`。
取消是正常生命周期，不应向用户弹出错误。

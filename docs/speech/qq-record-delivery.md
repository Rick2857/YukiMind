# QQ record 发送

Worker 生成 32 kHz 单声道 16 位 WAV 到共享缓存。主进程验证相对路径后读取字节，OneBot
Adapter 只在调用 `send_*_msg` 时构造 `record` 段和 `base64://...`；Base64 不进入数据库
或普通日志。这避开了 NapCat 容器无法访问 Bot 本地路径的问题。

发送一旦开始不会自动重试，以免出现重复语音。成功后 generation 标记为 sent；失败保留
真实类别并按场景回退文字。voice-only 账本保存实际朗读文本，text_and_voice 的语音段只保存
元数据，避免上下文重复正文；两种模式都不暴露本地路径。

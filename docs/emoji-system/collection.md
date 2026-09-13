# 自动收集

收集只针对当前收到的 OneBot 图片段，不回溯任意历史图片，也不触发聊天回复。

- `metadata_only`：仅 `emoji_id`、`emoji_package_id`、商城表情/贴纸 subtype 等明确元数据。
- `likely`：在上述基础上接受 label、summary、subtype 中带表情提示的图片。
- `all_images`：把当前作用域所有图片作为候选，视觉分类仍可将普通图片标为 `rejected`。

`emoji.collection_enabled`、`emoji.collect_private` 和 `emoji.collect_group` 分别控制总开关及场景。重复字节只增加 `seen_count/last_seen_at`；文件缺失时再次看到相同内容会恢复文件。`/ai emoji import` 是唯一确定性手工导入入口，只读取当前或回复图片。

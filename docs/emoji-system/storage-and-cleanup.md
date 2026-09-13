# 存储与清理

```text
data/emoji/
├── original/<sha-prefix>/<sha256>.<真实扩展名>
└── preview/<sha-prefix>/<sha256>.webp
```

原图以内容 SHA-256 命名并原子写入；PNG/JPEG/GIF/WebP 的扩展名由 Pillow 解码结果决定，不信任 URL 后缀。动画 GIF/WebP 原文件不转码，预览只使用第一帧。dHash 仅用于近似关系提示，近似资产可以共存。

周期维护和 `/ai emoji cleanup` 仅删除超过 `cache_retention_days` 的非 adopted、非 pinned 候选及残留临时文件。删除顺序先删数据库可删记录，再清理对应文件；正式池资产不受缓存清理影响。账本只保存安全摘要、MIME 和内部表情 ID，不保存 Base64。

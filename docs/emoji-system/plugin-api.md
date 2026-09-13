# Plugin API

Feature：`emoji.facade.v1`、`emoji.selection_signals.v1`。

权限：`emoji.read`、`emoji.collect`、`emoji.select`、`emoji.send`、`emoji.manage`、`emoji.hook`。`EmojiFacade` 提供安全元数据查询、当前图片收集、选择、排队回复效果和受控管理；不返回绝对路径、文件字节、签名 URL 或数据库对象。

通知事件覆盖 collected、analyzed、adopted、unadopted、rejected、banned、before/after select、queued、sent、send_failed、missing 和 restored。通知默认只观察；Hook 异常由 Host 隔离。第一版第三方插件只开放选择信号与通知事件，不替换核心分类器或生命周期。

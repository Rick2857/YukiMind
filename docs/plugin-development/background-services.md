# 后台服务

短生命周期轮询或缓存维护可以注册后台服务；用户定时任务必须使用 Automation。

```python
from yuki_plugin_sdk.models import RestartPolicy
from yuki_plugin_sdk.registrar import (
    BackgroundServiceMetadata,
    BackgroundServiceRegistration,
)


async def worker() -> None:
    while True:
        await run_one_bounded_iteration()
        await asyncio.sleep(30)


registrar.register_background_service(
    BackgroundServiceRegistration(
        metadata=BackgroundServiceMetadata(
            name="cache_refresh",
            description="刷新插件内存缓存",
            shutdown_timeout_seconds=5,
            max_concurrency=1,
            restart_policy=RestartPolicy.ON_FAILURE,
        ),
        runner=worker,
    )
)
```

需要 `background.worker`，并受 Manifest `limits.background_tasks` 和 Host `PLUGIN_BACKGROUND_TASK_LIMIT` 双重限制。

## 规则

- 不要创建未跟踪的永久 `asyncio.Task`。
- 临时派生任务使用 `ctx.scheduler.create_task(name, runner)`，并在停止时取消。
- 循环必须可取消，有限处理单批，避免同步阻塞。
- `ON_FAILURE` 不是无限快速重启；Host 失败阈值可禁用插件。
- 不在内存后台任务中实现持久提醒、定时发送或跨重启业务流程。
- `stop()` 必须让任务在声明的关闭超时内结束。


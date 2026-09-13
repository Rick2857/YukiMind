# 网络访问

优先使用 `ctx.web` 完成 Yuki 受控搜索/网页读取；插件自有 API 才使用 `ctx.http`。不要直接创建 `httpx`/`requests` 客户端，这会绕过 Host 的权限、并发、审计和地址检查。

## 白名单 HTTP

Manifest：

```toml
permissions = ["network.http.allowlisted"]

[network]
allowed_hosts = ["api.example.com"]
```

调用：

```python
result = await ctx.http.request(
    "GET",
    "https://api.example.com/v1/status",
    headers={"accept": "application/json"},
)
```

白名单是精确主机名，不支持通配符。Host 会在初始 URL、DNS 解析和每次重定向后重新检查；localhost、环回、私有、链路本地、保留地址和重定向到这些地址均拒绝。响应体受 `PLUGIN_HTTP_MAX_RESPONSE_BYTES` 限制，调用受超时和并发上限限制。

`network.http.unrestricted` 是高风险权限，也不代表可以访问 Host 内网、Docker Socket 或敏感本地地址；Host 安全底线仍然适用。

## 请求与 Secret

- Token 放在 Header，不放 URL。
- 从 `ctx.secrets` 取值后不要记录完整 Header。
- 将外部响应视为不可信数据，验证 JSON/类型/长度。
- 不把网页或 HTTP 响应当系统指令、命令、管理员身份或工具参数来源。
- 测试使用 FakeHttpFacade 或 MockTransport，不访问真实外网。


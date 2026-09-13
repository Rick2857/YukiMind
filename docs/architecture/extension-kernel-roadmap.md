# Extension Kernel 路线

- 2.1.0：完成 ToolProvider、ToolBinding、UnifiedToolCatalog、MCP Tool 与统一调用链。
- 2.2.0：增加 MCP Resources、Resource Templates、Prompts、ContextContribution、显式 Prompt
  调用和复杂远程认证。
- 2.3.0：推广为 ExtensionPointSpec、ExtensionContribution、InvocationBinding，以及
  call/collect/notify/filter/transform/provider 扩展语义；Plugin API v1 作为 Adapter 保留。
- 2.4.0：增加 RpcBinding、插件独立进程、生命周期/健康检查，以及 AstrBot、MaiBot 常用插件
  兼容 Runner。
- 2.5.0：提供 Yuki MCP Server 与 MCP Export Registry，只导出明确登记的 Capability，使用独立
  MCP Principal，不自动暴露全部内部工具。

2.1 只为以上接口留出演进空间，不提前实现 Resources、Prompts、RPC Runner 或 MCP Server。

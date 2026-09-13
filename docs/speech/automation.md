# 自动化语音

自动化注册 `speech.send_private` 与 `speech.send_group`，参数为 text、style_hint、可空的
profile_id 和目标 QQ/群号。普通用户只能发送给本人，或创建任务时的当前群；超级管理员仍
使用既有 DelegatedAuthority。创建时必须明确 profile，或明确使用当前默认档案。

执行时会重新检查自动化开关、目标作用域、档案启用状态和 Worker 健康，成功发送后更新
generation 并写永久账本。自动化不能导入模型、转换模型或动态从网页/OCR/历史拼出 profile。

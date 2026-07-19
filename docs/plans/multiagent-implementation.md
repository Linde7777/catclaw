# Multi Agent 实施记录

## 已确认目标

- main、普通 subagent、summarizer、decider 复用同一套活动时间线 UI。
- 只统一展示事件，不统一运行生命周期；memory manager 保持简单 runner。
- 普通 subagent 使用轻量 runner，不启动 memory manager，但完整聊天记录必须落盘供审查。
- 用户 UI 只能向 main 发送 steer message 和暂停/恢复；subagent 只接收 Agent 间消息。
- `create_subagent` 异步启动唯一命名的 subagent；`send_msg_to_agent` 通过 steer message 通信。
- Agent 间消息由系统添加 `<msg from="...">...</msg>`，发件人不可由模型指定。

## 分层

```text
WebSocketChatSession -> AgentTeam -> main AgentRunner
                              \-> lightweight subagent runner
                              \-> summarizer/decider runner
所有 runner -> AgentActivityEvent -> 主时间线 / 右侧 Inspector
```

顶层协议由 `AgentTeam` 表达；`WebSocketChatSession` 和 Agent 通信工具只依赖该协议。
subagent runner 只暴露首次启动和接收 Agent 消息，memory manager 仅注册 activity。

## 实施顺序

1. 定义带 Agent 身份的统一活动事件，并接入 memory manager。
2. 实现右侧 Inspector，复用现有 user/assistant/tool 时间线。
3. 把 subagent 记录按 main conversation 分目录落盘，但默认不恢复运行。
4. 实现 `AgentTeam`、两个通信工具和生命周期管理。
5. 补充重连、并发、名称冲突及端到端测试。

## 当前假设

- `main` 是主 Agent 的保留名称；用户创建的名称使用受限标识符。
- 每次 summarizer/decider 唤醒在 UI 中是独立活动，而非持续对话。
- subagent 结束后销毁运行实例，磁盘记录保留；程序重启后只供审查。

## 待后续确认

- 审查历史是仅随 main conversation 恢复时展示，还是需要独立的历史浏览入口。

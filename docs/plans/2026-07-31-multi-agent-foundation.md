# Multi-agent 基础方案

## 目标

- 用右侧面板展示 worker、subagent、summarizer 和 decider 的完整工作过程。
- 所有 agent 复用同一套运行事件、持久化格式和前端时间线。
- 普通 agent 可以创建 subagent，并通过 steer conversation 互相发送消息。

## 核心结构

`AgentTeam` 管理 agent 树、名字检查、消息路由、运行状态和事件订阅。
`WebSocketChatSession` 只转发命令并订阅事件，不拥有 agent 的业务生命周期。
worker 和 subagent 使用 `Agent + AgentRunner`。
summarizer 和 decider 的每次唤醒都是独立的一次性运行，不支持暂停、steer 或接收 agent 消息。

每个实例包含 `agent_id`、`name`、`role`、`parent_agent_id` 和 `status`。
`agent_id` 是持久化与事件标识，`name` 是当前 conversation 内唯一的显示和路由名称。
`role` 表示 `worker`、`summarizer` 或 `decider`，不表示 main 或 subagent。
`parent_agent_id` 为空的 worker 是根 agent，其余 agent 都通过父节点形成任意深度的树。
memory manager 使用 `summarizer-<序号>` 和 `decider-<序号>` 保留名称，reset context 后从 1 重新计数。

## 消息与工具

`Agent` 新增私有 `_enqueue_message()`，统一处理排队、自动恢复和回调。
`enqueue_user_message()` 保存 `frontend_msg_id` 后调用它。
`enqueue_agent_message()` 保存发送者信息并调用它。
agent 消息在进入目标队列前包装为 `<msg from="A">content</msg>`。

新增 `create_subagent(name, first_msg)` 和 `send_msg_to_agent(agent_name, msg)`。
发送消息只负责入队并启动目标 runner，不等待目标完成。
subagent 默认不能创建子 agent，配置打开后才获得 `create_subagent`。

## 事件、持久化与 UI

所有运行事件携带 `agent_id`，并保留 reasoning、content、工具参数和工具结果。
每个 agent 保存独立聊天记录，不能使用全局 `load_latest()` 恢复其他 agent 的记录。
memory manager 记录 fork 后收到的任务和执行过程，不复制 worker 的既有时间线。
统一记录替代 `MemoryManagerRunLogger` 后，删除该类及旧 JSONL 写入逻辑。

前端保存 `agent_id -> timeline`，主区域继续显示 worker。
右侧面板按父子关系显示 agent 树、角色和状态。
用户选择一个 agent 后，面板复用现有消息与工具组件展示其时间线。

## 实施顺序与暂不实现

先建立 AgentTeam、统一事件和独立记录的骨架。
再接入 memory manager，并删除旧 logger。
然后实现右侧面板、subagent 工具和跨 agent 消息。
本次不实现 WebSocket 断开后继续运行。
未来把 AgentTeam 放到应用生命周期中，断线只取消订阅，agent 继续运行并持久化。

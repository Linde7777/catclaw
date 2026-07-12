那就继续吧。那咱就开干吧。那咱们就开干吧！# Multi Agent Orchestrator 实施计划

> 状态：方案已获用户确认，代码实施尚未开始。开始实施后遵循 `plan-coding`：自顶向下推进，每次代码改动不超过 100 行，等待用户确认后用 `partial-feat/refactor/fix:...` 前缀提交，再继续下一段；设计发生变化时同步更新本文档。

## 目标与边界

系统增加可嵌套的临时 subagent，并用右侧面板展示主 Agent、subagent、summarizer、decider 各自的完整运行过程。复用边界是聊天事件协议和时间线 UI，不强制普通 Agent 与 memory manager 使用相同 runner。

本计划采用以下产品假设：

- Agent 名称在一次 `WebSocketChatSession` 内唯一；内部另用不可变 `agent_id` 做路由和前端 key。
- 普通 subagent 只活在当前 WebSocket 会话中，不恢复历史、不写 conversation JSON、不启用 memory manager；断线后随 session 销毁。
- subagent 可以继续创建 subagent；不预设层级或数量限制，名称仍按整个 session 全局唯一。
- `send_msg_to_agent` 只支持普通主 Agent/subagent，summarizer 和 decider 是不可 steer 的一次性运行实例。
- memory manager 面板不重复展示 fork 得到的 worker 历史，只展示本次唤醒追加的角色指令及其后的推理、回答、工具和结果。
- 主输入框、暂停和恢复仍只控制主 Agent；侧栏第一版只负责查看，不直接给 subagent 手工发消息。

不做跨重连持久化、Agent 权限系统、并发数限制、任务取消、会话历史列表或已有 conversation 文件迁移。后续确有需求时再扩展，不提前加入占位抽象。

## 总体设计

新增 `AgentOrchestrator` 作为一个 WebSocket session 内的多 Agent 运行时注册表和路由器。`WebSocketChatSession` 只处理传输协议，把主 Agent 输入交给 Orchestrator，并接收其统一输出；`AgentRunner` 继续只驱动单个 `Agent`。

```text
WebSocketChatSession
  │ 输入命令                         ▲ 带 agentId 的输出事件
  ▼                                  │
AgentOrchestrator ────────────────────┘
  │
  ├── AgentHandle(main) ── AgentRunner ── Agent
  ├── AgentHandle(subagent) ─ AgentRunner ─ Agent
  ├── AgentHandle(summarizer run) ─ SummarizerRunner
  └── AgentHandle(decider run) ──── DeciderRunner
```

Orchestrator 负责：注册表、名称唯一性、父子关系、生命周期、创建 subagent、Agent 间消息路由，以及给所有前端事件添加 `agentId`。它不负责模型流式生成、工具执行、conversation 落盘或 WebSocket I/O。

### Agent 身份与注册表

后端新增最小运行时模型：

```python
AgentKind = Literal["main", "subagent", "summarizer", "decider"]
AgentStatus = Literal["idle", "running", "completed", "failed"]

@dataclass
class AgentHandle:
    id: str
    name: str
    kind: AgentKind
    parent_id: str | None
    status: AgentStatus
    runner: AgentRunner | None
```

`agent_id` 由系统生成，主 Agent 使用 session 内固定 ID；`name` 用于模型工具参数和 UI。memory manager 每次唤醒都注册为新实例，例如 `summarizer-3`，完成后保留 handle 和前端时间线，但不保留可运行 runner。

### 输入、工具与消息路由

`create_subagent` 和 `send_msg_to_agent` 的 schema/参数校验分别放在独立工具模块；handler 由 Orchestrator 创建并绑定 `caller_agent_id`。工具只是模型适配层，实际名称检查、创建与路由都调用 Orchestrator 方法。

```text
模型 tool call
  → Tool.handler（已绑定 caller_agent_id）
  → AgentOrchestrator.create_subagent/send_message
  → 目标 AgentRunner.submit_user_message
```

接口语义固定为：

- `create_subagent(caller_id, name, first_msg)`：名称 trim 后不能为空且不能重复；创建成功后先发布 `agent.created`，再以系统生成的内部 message ID 提交 `first_msg`，返回新 Agent 的名称和 ID。
- `send_message(sender_id, target_name, msg)`：按全局唯一名称查找目标，拒绝不存在或不可 steer 的目标，把内容包装为 `<msg from="发送者名称">...</msg>` 后调用目标 runner 的 `submit_user_message()`。
- XML 属性值和正文必须转义，防止名称或消息破坏信封结构；目标模型只收到包装后的字符串。
- handler 返回短小、结构稳定的成功或错误结果；业务错误作为工具结果返回，不让一次无效路由击穿整个 AgentRunner。

所有普通 Agent 都注入这两个工具，因此支持嵌套创建和双向通信。每个 Agent 持有独立 `CwdState`；subagent 初始 cwd 复制父 Agent 创建时的当前 cwd，之后互不影响，也不写 worker 的 cwd 持久化文件。

### 临时 Agent 的会话状态

当前 `Agent` 固定依赖 `ConversationStore`，会恢复全局最新历史、落盘并唤醒 memory manager，不能直接用于临时 subagent。先提取一个仅覆盖 `Agent` 实际所需操作的 conversation state/store 协议：持久实现继续委托现有 `ConversationStore`，临时实现只在内存保存 messages、started 和 pause 状态。

Agent 构造时注入 store/lifecycle 策略，而不是到处判断 `is_subagent`：

- 主 Agent 使用“恢复最新或新建”的持久 store，并启用现有 memory manager。
- subagent 使用全新 transient store，初始只有自己的 init messages，并禁用 memory manager。
- `Agent.start_conversation()`、消息追加和 `drive_decision()` 只依赖统一 store 接口；主 Agent 的 reset-context 与 memory manager meta 仍由持久实现承载。

memory manager 开关保持一个明确布尔能力即可，不引入通用插件框架。subagent 的 init prompt 在普通 worker 指令后追加身份说明：它是由父 Agent 创建的临时 subagent、没有长期记忆、应完成分配任务并通过 `send_msg_to_agent` 汇报或协作。

### 统一输出事件

把当前 `ChatEventProjector` 从 WebSocket session 文件移到独立模块，使主 Agent、subagent 和 memory manager adapter 都能复用。Orchestrator 暴露的输出方法命名为 `emit_agent_event()`，避免误解为消息队列 Pub/Sub：

```python
def emit_agent_event(self, *, agent_id: str, event: dict[str, Any]) -> None:
    self._emit({"type": "agent.event", "agentId": agent_id, "event": event})
```

它只包装并转发已发生的事件，不驱动 runner。Agent 的流式/工具回调和 AgentRunner 的 busy/idle/turn 回调都绑定到对应 agent 的 projector；`conversation.switched` 只会出现在主 Agent 的内层事件中。

外层协议包含：

- `agent.snapshot`：session 初始化时一次性发送当前 Agent 元数据列表；首版通常只有主 Agent。
- `agent.created`：包含 `id/name/kind/parentId/status`，必须先于该 Agent 的任何聊天事件。
- `agent.status.changed`：状态变化为 `running/idle/completed/failed`；普通 Agent idle 后仍可被 steer，memory manager 结束后为 completed。
- `agent.event`：包含 `agentId` 和一个现有聊天事件。全局连接错误仍保留顶层 `error`；单个 Agent 运行错误同时标记 failed，并作为该 Agent 的内层 error 发出。

现有聊天事件不增加 `agentId` 字段，以便前端继续复用单时间线 reducer，也避免每个 schema 重复声明身份字段。

## Memory Manager 接入

保留 `SummarizerRunner` 和 `DeciderRunner` 的控制流及返回值。为它们增加可选 observer/callback bundle，默认仍为 `noop`，所以脱离 WebSocket 的调用和现有测试不受影响。

每次 `_maybe_wake_memory_manager()` 创建 task 前，通过 Agent 注入的 memory-manager run observer factory 注册一次性 handle，并取得绑定 agent ID 的 observer：

```text
注册 summarizer/decider handle
  → 发布 agent.created
  → observer 先投影本次角色指令为 user.message.committed
  → stream/tool callbacks 进入同一个 ChatEventProjector
  → runner finished/failed 更新 Agent 状态
```

`MemoryManagerRunLogger` 继续保留为磁盘审计来源；UI observer 是旁路观察，不能替代日志，也不能改变 decider 的 `bool` 结果、summarizer 工具集合或 provider 工具缓存形状。observer 自身异常必须记录并隔离，不能让 UI 故障影响记忆管理。

## 前端状态与界面

协议层用 zod 增加 Agent 元数据、外层生命周期事件和 `agent.event`，内层继续复用现有聊天事件 schema。Store 调整为连接级状态加按 Agent 隔离的时间线：

```typescript
type MultiAgentState = {
  agents: AgentSummary[]
  chatsByAgentId: Record<string, ChatState>
  mainAgentId: string | null
  selectedSideAgentId: string | null
}
```

先把现有 `reduceServerEvent` 拆成可复用的纯 `reduceChatEvent(chat, event)`；收到 `agent.event` 时只更新对应 `chatsByAgentId[agentId]`。连接状态仍是全局状态，主输入的 pending message 只写主 Agent chat。selector 必须返回稳定引用，避免 Zustand 5 无限更新。

从 `App.tsx` 提取无输入框的 `ChatTimeline`，主区域和侧栏详情共同使用。桌面端右侧为可开合 panel：顶部显示按父子关系缩进的 Agent 列表与状态，选中后展示该 Agent 时间线；移动端使用覆盖式 drawer，避免压缩主聊天区。主页面的输入、暂停、自动滚动和“跳到最新”行为保持不变；侧栏时间线维护自己的滚动容器，不抢主时间线滚动。

## 实施顺序

### 阶段一：普通 subagent 闭环

1. 提取持久/临时 conversation store 边界，让相同 `Agent` 能以无持久化、无 memory manager 模式运行；先用单元测试锁住主 Agent 原行为。
2. 新增 Agent 工具模块和 Orchestrator 注册表，接入主 Agent 创建、嵌套 subagent、名称校验、XML 消息路由及 session 关闭清理。
3. 独立 `ChatEventProjector`，升级 WebSocket 外层 Agent 协议，同时保持内层聊天事件语义不变。
4. 前端改为多 Agent store，提取时间线并完成右侧 panel/移动 drawer。
5. 完成普通 subagent 的后端集成测试和浏览器端到端测试，再进入阶段二。

### 阶段二：Memory Manager 可视化

1. 给 summarizer/decider 增加可选 observer，透传现有 stream/tool 回调，不改其决策逻辑和工具形状。
2. 在主 Agent 唤醒点注册每轮 memory manager 实例，投影指令、运行事件与结束状态，同时继续写现有 JSONL 日志。
3. 前端用既有 Agent 列表与时间线直接显示两类实例，仅补充 kind 标签和 completed/failed 状态，无第二套 UI。

## 测试计划

后端单元测试覆盖：

- transient store 不读取/创建 conversation 文件，消息链和 `drive_decision()` 仍能正常推进，且永不唤醒 memory manager。
- 创建工具校验空名称、重复名称，成功时绑定父 Agent、复制 cwd 并先发 created 事件。
- 发送工具正确查找目标、转义 XML、保留 sender 身份，并拒绝未知目标及 memory manager 目标。
- 并发运行的两个 Agent 事件具有正确 `agentId`，message/tool ID 不会串到另一条时间线。
- session 关闭后不再接收事件并清理/停止临时 runner task；主 Agent 原持久化、暂停和 reset 测试不回归。
- summarizer/decider observer 收到角色指令、delta、tool 和完成/失败事件；observer 失败不影响日志、摘要执行或 decider 返回值。

前端测试覆盖 reducer 的 Agent 创建、状态转换、按 ID 隔离事件、未知 Agent 事件处理、主 conversation 切换不清空 subagent chat，以及重连 reset 后清理上一 session 的临时 Agent。

端到端测试使用 mock model 的确定性 tool-call 场景验证：主 Agent 创建 subagent、侧栏先出现 Agent 再流式显示其时间线、subagent 给主 Agent 发消息并触发主 Agent 后续回合、重复名称显示工具错误、桌面 panel 与移动 drawer 均可查看已完成过程。阶段二再增加一次 summarizer/decider 唤醒可见性场景。

验证命令：

```bash
cd backend && uv run pytest -q --tb=line
cd frontend && npm run lint
cd frontend && npm run build
cd frontend && npm run test:e2e
```

## 主要风险与约束

- 最大回归风险是为 transient store 解耦时破坏主 Agent 的落盘/reset 不变量；必须先建立 store 契约测试，不能用散落的 `if ephemeral` 修补。
- Agent 之间可以并发调用并互相 steer，但每个 Agent 内仍由各自 `AgentRunner` 防重入；Orchestrator 不增加全局串行锁。
- `send_msg_to_agent` 可能形成 Agent 间无限对话。本阶段按用户要求不加任意轮数限制；日志必须包含 sender/target，后续根据真实问题再增加预算或取消机制。
- 关闭 session 时现有 `AgentRunner` 没有显式 shutdown API。实施时应增加幂等 `close()`，取消并等待其 task；否则临时 Agent 可能在 WebSocket 消失后继续消耗模型资源。
- 事件顺序依赖同步 `put_nowait`：`agent.created` 必须在该 Agent 的首条 `agent.event` 前发出，不能为事件投递另开无序后台 task。

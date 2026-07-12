背景是这样的，我这个 agent 系统不是会自动 fork agent出来吗，就是 fork summarizer和decider出来，我这个系统将来也是要做 Multi Agent 支持的，然后呢，我现在 summarizer 和 decoder 的它的工作过程都是通过日志来显示的，就是不太方便嘛，就是所以说因为我将来也要做 multi agent，那么所以我也要专门做个 UI 出来。那么我就希望现在这个 summarizer 和 decoder 也能复用这个multiagent的相关的前端和（或者）后端代码。

ui方面，是要弄一个类似side panel的效果，在右边侧边栏里面弄，你可以查看每个 subagent 的 完整工作过程，是你看它的过程就是和我们看主agent的工作过程是一样的。

agent可以创建subagent，subagent没有任何记忆机制，它们是临时创建的，用来给agent减轻上下文压力

要有一个工具叫做Create subagent，参数是subagent的名字（要是唯一的）。还有一个first msg参数，就是就是给这个subagent的第一句话，就是说交给他的任务吧。

我要做基于Steer conversation做一个multiagent沟通机制。

要有一个工具叫做send_msg_to_agent，参数agent_name和msg，底层就是通过submit user message

agent A调用这个工具给agent B发送消息时，agent B会收到：
```
<msg from="A">some content</msg>
```
这个xml是系统自动加上的

我感觉应该要在 WebSocket chat session 和 Agent Runner 之间，应该是要在加一个抽象，这个抽象会包住 Agent Runner， 就是说这抽象是专门用来处理多 Agent 的。

---

这里的核心不是让所有角色继承同一个类，而是让它们对前端表现为同一种“事件源”。

可以把它拆成三层：

```text
不同的内部实现
─────────────────────────────────────────────────────────

主 Agent / 普通 subagent                summarizer / decider
Agent + AgentRunner                     现有专用 Runner
        │                                      │
        │ Agent callbacks                      │ stream/tool callbacks
        ▼                                      ▼

统一的事件投影层
─────────────────────────────────────────────────────────

ChatEventProjector                 MemoryManagerEventAdapter
        │                                      │
        └─────────── 标准 ChatEvent ───────────┘
                             │
                             ▼

AgentOrchestrator
publish(agent_id, event)
                             │
                             ▼

WebSocket
{
  "type": "agent.event",
  "agentId": "subagent-research-7f31",
  "event": {
    "type": "assistant.message.delta",
    "messageId": "...",
    "channel": "content",
    "delta": "..."
  }
}
                             │
                             ▼

前端 Map<agentId, ChatState>
```

## 1. 什么是“带 agentId 的聊天事件”

目前 `WebSocketChatSession` 发出的事件大致是：

```json
{
  "type": "assistant.message.delta",
  "messageId": "message-1",
  "channel": "content",
  "delta": "正在分析..."
}
```

它没有说明这是哪个 agent 发出的，因为现在系统里只有一个展示给用户的 worker。

Multi Agent 后，主 agent、subagent 和 summarizer 可能同时输出内容。如果仍使用原协议，前端无法判断一段 delta 应该追加到哪条时间线。

因此，可以在外面包一层：

```json
{
  "type": "agent.event",
  "agentId": "subagent-research-7f31",
  "event": {
    "type": "assistant.message.delta",
    "messageId": "message-1",
    "channel": "content",
    "delta": "正在分析..."
  }
}
```

其中：

- `agentId` 是系统生成的内部稳定标识。
- `agentName` 是用户或模型指定的可读名称，例如 `researcher`。
- 内层 `event` 仍然使用现有聊天协议。
- `messageId` 只需在单个 agent 内唯一；前端状态按 `agentId` 隔离。

另外还需要少量不属于聊天时间线的 Agent 级事件：

```json
{
  "type": "agent.created",
  "agent": {
    "id": "subagent-research-7f31",
    "name": "researcher",
    "kind": "subagent",
    "parentId": "main"
  }
}
```

```json
{
  "type": "agent.status.changed",
  "agentId": "subagent-research-7f31",
  "status": "running"
}
```

这些事件用于侧边栏显示 Agent 列表、父子关系和运行状态。

## 2. 普通 subagent 怎么接进来

普通 subagent 的工作方式与主 Agent 基本一致：

```text
create_subagent(name, first_msg)
        │
        ▼
AgentOrchestrator.create_subagent(...)
        │
        ├── 检查名称是否唯一
        ├── 创建独立 CwdState
        ├── 创建 Agent
        ├── 创建 AgentRunner
        ├── 注册到 agents_by_id
        ├── 发布 agent.created
        └── runner.submit_user_message(first_msg)
```

Orchestrator 维护类似这样的注册表：

```python
@dataclass
class AgentHandle:
    id: str
    name: str
    kind: Literal["main", "subagent", "summarizer", "decider"]
    parent_id: str | None
    runner: AgentRunner | None
    status: AgentStatus
```

普通 subagent 创建 `Agent` 时，仍然传入这些已有回调：

```python
on_ai_content_delta
on_ai_reasoning_delta
on_ai_tool_call_started
on_tool_result
```

但回调不再直接向 WebSocket 发裸事件，而是经过绑定了 `agent_id` 的 projector：

```python
projector = ChatEventProjector(
    emit=lambda event: orchestrator.publish(
        agent_id=subagent_id,
        event=event,
    )
)
```

因此 `Agent` 和 `AgentRunner` 不需要理解 WebSocket，也不需要知道右侧面板的存在。

## 3. summarizer / decider 怎么接进来

目前它们直接调用：

```python
await stream(
    ...,
    on_ai_content_delta=noop,
    on_ai_reasoning_delta=noop,
    ...
)
```

工具结果也是：

```python
on_tool_result=noop
```

所以运行过程只有 `MemoryManagerRunLogger` 能看到。

方案一不会把它们改造成 `Agent`，而是给现有 runner 增加一个可选的事件观察接口。例如：

```python
class MemoryManagerRunObserver(Protocol):
    def on_started(self, ...) -> None: ...
    def on_ai_content_delta(self, ...) -> None: ...
    def on_ai_reasoning_delta(self, ...) -> None: ...
    def on_ai_tool_call_started(self, ...) -> None: ...
    def on_tool_result(self, ...) -> None: ...
    def on_finished(self, ...) -> None: ...
```

随后把 `noop` 替换为 observer 对应的回调：

```python
await stream(
    ...,
    on_ai_content_delta=observer.on_ai_content_delta,
    on_ai_reasoning_delta=observer.on_ai_reasoning_delta,
    ...
)
```

这个 observer 内部仍然使用 `ChatEventProjector`，把底层流式回调转换成与普通 Agent 相同的事件：

```text
summarizer 的 stream delta
        │
        ▼
MemoryManagerRunObserver
        │
        ▼
ChatEventProjector
        │
        ▼
orchestrator.publish(summarizer_agent_id, chat_event)
```

这样，summarizer 不需要拥有以下普通 Agent 才需要的能力：

- `ConversationStore`
- user message queue
- pause/resume
- `drive_decision()`
- 长期对话恢复
- `AgentRunner._run_until_idle()`

但前端仍能看到：

```text
summarizer
├── 收到的本次总结指令
├── reasoning 流
├── assistant content 流
├── 工具调用参数
├── 工具结果
└── completed / failed 状态
```

decider 也是相同做法，只是它的内部 runner 最终还要向调用方返回 `bool`。UI 事件只是旁路观察，不改变这个返回值。

## 4. Orchestrator 到底负责什么

它不是用来执行模型推理的，而是管理多个执行单元之间的关系：

```text
AgentOrchestrator
├── Agent 注册表
├── 名称唯一性
├── 父子关系
├── 生命周期状态
├── 创建普通 subagent
├── Agent 间消息路由
├── 统一事件出口
└── 连接关闭时清理临时 subagent
```

例如 Agent A 调用：

```text
send_msg_to_agent(agent_name="researcher", msg="继续检查数据库层")
```

处理过程是：

```text
Agent A
  │ send_msg_to_agent
  ▼
AgentOrchestrator
  │ 查找 researcher
  │ 确认目标支持接收消息
  │ 包装来源信息
  ▼
researcher.runner.submit_user_message(
    '<msg from="A">继续检查数据库层</msg>'
)
```

这里不能让工具直接持有另一个 `AgentRunner`，否则 Agent 之间会形成难以管理的对象引用。所有路由统一经过 orchestrator。

summarizer 和 decider 默认不接受 `send_msg_to_agent`，因为它们不是可 steer 的长期对话。Orchestrator 可以通过 `kind` 或 capability 明确拒绝，而不是让调用最终在内部异常。

## 5. 前端如何复用同一个聊天 UI

当前前端只有一个：

```typescript
ChatState
```

改成：

```typescript
type MultiAgentState = {
  agents: AgentSummary[]
  chatsByAgentId: Record<string, ChatState>
  selectedAgentId: string
}
```

收到事件时：

```typescript
applyAgentEvent(agentId, event)
```

内部继续调用现有的聊天事件 reducer：

```typescript
chatsByAgentId[agentId] = reduceChatEvent(
  chatsByAgentId[agentId],
  event,
)
```

因此主页面和右侧面板可以复用相同的时间线组件：

```tsx
<ChatTimeline chat={chatsByAgentId[selectedAgentId]} />
```

区别只是：

- 主区域固定展示主 Agent。
- 右侧栏列出 subagent、summarizer、decider。
- 点击某个 Agent 后，侧栏详情使用同一个 `ChatTimeline` 展示它的过程。
- memory manager 可以被标记为一次性运行实例，例如 `summarizer #3`，而不是把多次唤醒混到同一条时间线。

一句话概括：**内部继续允许两种 runner 存在，外部通过 adapter 把两者转换成相同的聊天事件，再由 orchestrator 给事件标记所属 Agent 并统一送往前端。**

## 6. `publish(agent_id, event)` 到底是什么

`publish()` 不是 `AgentRunner` 的现有接口，也不应该加到 `AgentRunner` 上。它只是 `AgentOrchestrator` 自己的统一事件出口，用来回答两个问题：

1. 这条事件属于哪个 Agent？
2. 这条事件最终应该发到哪里？

现有代码里，真正产生运行事件的是两组回调：

- `Agent` 触发内容增量、reasoning 增量、工具调用和工具结果等回调。
- `AgentRunner` 触发 busy、idle 和 turn completed 等生命周期回调。

`AgentRunner` 仍然只负责驱动一个 Agent，不需要知道其他 Agent，也不需要提供 `publish()`：

```text
Agent.run()
  │
  ├── on_ai_content_delta(...)
  ├── on_ai_tool_call_started(...)
  └── on_tool_result(...)
             │
             ▼
      ChatEventProjector
             │ 生成现有聊天事件
             ▼
orchestrator.publish(agent_id, event)
             │ 添加 agentId 外层信封
             ▼
WebSocketChatSession._emit_sync(...)
             │
             ▼
       WebSocket 发送队列
```

具体连接方式可以是构造回调时闭包绑定 `agent_id`：

```python
projector = ChatEventProjector(
    emit=lambda event: orchestrator.publish(
        agent_id=agent_id,
        event=event,
    )
)

agent = Agent(
    ...,
    on_ai_content_delta=projector.on_ai_content_delta,
    on_tool_result=projector.on_tool_result,
)

runner = AgentRunner(
    agent=agent,
    ...,
    on_agent_became_busy=lambda: orchestrator.publish(
        agent_id=agent_id,
        event={"type": "agent.became.busy"},
    ),
)
```

Orchestrator 自身也不直接操作 WebSocket。`WebSocketChatSession` 在创建 Orchestrator 时，把自己的同步事件发送函数注入进去：

```python
class AgentOrchestrator:
    def __init__(self, *, emit: EventEmitter) -> None:
        self._emit = emit

    def publish(self, *, agent_id: str, event: dict[str, Any]) -> None:
        if agent_id not in self._agents:
            raise ValueError(f"未知的 agent_id: {agent_id}")

        self._emit(
            {
                "type": "agent.event",
                "agentId": agent_id,
                "event": event,
            }
        )
```

因此，`publish()` 与 `submit_user_message()` 属于两个方向完全不同的接口：

```text
输入/控制方向：WebSocket 或其他 Agent
                    │
                    ▼
             AgentOrchestrator
                    │
                    ▼
 AgentRunner.submit_user_message(...)

输出/观察方向：Agent 和 AgentRunner 回调
                    │
                    ▼
 AgentOrchestrator.publish(...)
                    │
                    ▼
                 WebSocket
```

- `submit_user_message()` 是把输入送进某个 Agent，可能触发该 Agent 继续运行。
- `publish()` 是把已经发生的运行过程通知给前端，不驱动 Agent，也不改变 Agent 状态。

不过，`publish` 这个名字确实容易让人误以为它是消息队列或 Pub/Sub 抽象。正式实现时可以命名为 `emit_agent_event()`，语义会更直接：

```python
orchestrator.emit_agent_event(agent_id=agent_id, event=event)
```

它本质上是“给事件加上所属 Agent 的标识后，从统一出口发出”，而不是新的 runner 协议。

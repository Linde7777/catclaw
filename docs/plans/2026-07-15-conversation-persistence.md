# Conversation 持久化重构

## 目标

- `conversation_state.py` 中只有一个扁平的 `ConversationState`，避免为字段分组增加无行为的类型。
- 内存中只保留一份会话状态，避免 `Agent` 与持久化层手动同步。
- `ConversationRepository` 只负责加载和持久化完整快照。
- 保留 JSON 的可读性与原子替换，不引入 pickle 或 SQLite。

## 已确认规则

- 新建会话只创建内存中的 `ConversationState`，不立即创建文件。
- 收到首条真实用户消息后，`Agent` 才调用 `persist()`。
- `persist()` 首次执行时分配文件名，后续执行覆盖同一文件。
- `messages` 只保存真实对话；调用模型时临时拼接 `init_messages + messages`。
- 不兼容旧 JSON 格式，迁移后按新结构读写。

## 目标结构

```text
Agent -> ConversationState -> ConversationRepository.persist() -> JSON
                 ^
启动时             | ConversationRepository.load_latest()
```

## 渐进步骤

1. [完成] 加入扁平的 `ConversationState` 状态骨架。
2. [完成] 加入 `ConversationRepository.load_latest()` / `persist()` 和序列化测试。
3. [完成] 让 Agent 只持有一份 `ConversationState`；Repository 通过构造参数注入。
4. [完成] 删除旧 `conversation_store.py` 和 `test_conversation_store.py`。
5. [完成] 更新 `agent_runner.py` 中的旧 Store 注释，运行后端完整测试。
6. [完成] 检查一次业务边界的 JSON 重写次数，避免同一边界重复 persist。

## 当前检查点（2026-07-15）

- Agent 已不再引用 `ConversationStore`；旧 Store 只被自己的旧单测引用。
- 已迁移恢复、pause、memory manager、reset carryover 及 Agent 测试夹具。
- 相关测试命令：`cd backend && uv run pytest -q --tb=line tests/test_agent_callbacks.py tests/test_agent_memory_manager_background_task.py tests/test_resume_conversation.py tests/test_conversation_repository.py`
- 最近结果：`28 passed`。
- 删除旧文件后的完整后端测试：`80 passed, 3 skipped`。
- 新增 memory manager 聚合状态只持久化一次的回归测试；最终完整测试为 `81 passed, 3 skipped`。
- 工作树原有 `TODO.md` 修改属于用户，禁止撤销或覆盖。

## 待实现时验证

- 首条用户消息前不会生成空文件。
- 每个业务持久化边界只重写一次 JSON。
- reset 后的新 segment 仍能保存 carryover messages。

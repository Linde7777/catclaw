# 去掉显式 summarizer flag，改为隐性消息签名边界

## 目标

不再把 `WAKE_MM_SUMMARY_FLAG` 作为一条显式 user 消息插入 worker 上下文。  
改为在唤起 summarizer 时，记录一个仅供 summarizer / reset-context 使用的隐性边界：

- 对程序逻辑：记录边界消息在业务消息数组中的位置，作为精确引用
- 对 summarizer 提示词：附带一份AI和人类可读的消息签名，帮助它理解“上次处理到哪里”

## 设计

### 抽象

把“最近一次 summarizer 已处理到哪里”从“显式哨兵消息”改成“隐性边界元数据”：

```text
业务消息流
M1 M2 M3 M4
      ^
      唤起 summarizer 时记录 M3 的位置和签名

之后 reset / 下次 summarizer：
reset 要用到的 carryover 用位置精确截取
summarizer 用签名理解边界
```

### 实现思路

1. 在 `Agent._maybe_wake_memory_manager()` 唤起 summarizer 时，记录当前边界消息。
   边界消息就是“当时业务消息里的最后一条”：
   - 无 tool call 的路径里，最后一条是 assistant message
   - tool call 执行完成并 append tool message 的路径里，最后一条是 tool message

2. 生成一份AI和人类可读的边界签名：
   从“前 10 个字符 + 后 10 个字符”开始；
   若在当前业务消息列表里重复，则逐步扩窗；
   上限为 60 个字符；
   若到上限仍重复，则接受“按最近匹配处理”。

3. 把边界元数据写入 conversation 的 memory-manager 元数据，不再往 `_messages` 追加显式 flag 消息。
   元数据至少包含：
   - `last_summarized_msg_idx`
   - `last_summarized_signature`

4. summarizer fork 时继续拿 worker messages snapshot，但 summarizer 指令不再提 `WAKE_MM_SUMMARY_FLAG`。
   改为读取上述元数据，并告诉它：
   “你上一次被唤醒的边界是（对应的边界的消息的前x个字符）......（对应的边界的消息的后x个字符）”

5. reset carryover 改为直接使用 `last_summarized_msg_idx` 精确截取：
   `carryover = business_messages[index + 1 :]`
   不再在 reset 时根据签名重新扫描消息列表。

## 测试思路

1. 单测签名生成：
   唯一签名、需要扩窗、扩到 60 仍重复，这三类都要覆盖。

2. 单测边界记录：
   覆盖两条唤醒路径，确认记录到的都是“当时最后一条业务消息”的索引和签名。

3. 单测 carryover 截取：
   直接按记录的 business index 截取，确认不会再走“找不到匹配就全部保留”的退化路径。

4. 单测 summarizer 提示词：
   确认不再出现显式 flag 文案，改为说明“最近边界位置 + 可读签名”。

## 风险

- reset carryover 的锚点是强唯一的，因为它走业务消息索引。
- 签名只服务于 summarizer 的可读性，不参与程序级截取。
- 当大量重复消息导致签名到 60 字符仍不唯一时，summarizer 看到的签名会有歧义；这是可接受的，因为程序逻辑不依赖它做精确定位。

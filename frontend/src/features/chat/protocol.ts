import { z } from 'zod'

const nonEmptyString = z.string().min(1)

const agentBecameBusyEventSchema = z.object({
  type: z.literal('agent.became.busy'),
})

const agentBecameIdleEventSchema = z.object({
  type: z.literal('agent.became.idle'),
})

const agentPauseRequestedEventSchema = z.object({
  type: z.literal('agent.pause.requested'),
})

const agentPausedEventSchema = z.object({
  type: z.literal('agent.paused'),
})

const agentResumedEventSchema = z.object({
  type: z.literal('agent.resumed'),
})

const visibleToolCallSchema = z
  .object({
    id: nonEmptyString.optional(),
    function: z
      .object({
        name: z.string().optional(),
        arguments: z.string().optional(),
      })
      .optional(),
  })
  .passthrough()

const visibleConversationMessageSchema = z
  .object({
    role: z.enum(['user', 'assistant', 'tool']),
    content: z.string().nullable().optional(),
    reasoning_content: z.string().nullable().optional(),
    tool_call_id: z.string().optional(),
    name: z.string().optional(),
    tool_calls: z.array(visibleToolCallSchema).optional(),
  })
  .passthrough()

const conversationSwitchedEventSchema = z.object({
  type: z.literal('conversation.switched'),
  visibleMessages: z.array(visibleConversationMessageSchema),
})

const userMessageCommittedEventSchema = z.object({
  type: z.literal('user.message.committed'),
  userMessageId: nonEmptyString,
  content: z.string(),
})

const assistantMessageStartedEventSchema = z.object({
  type: z.literal('assistant.message.started'),
  messageId: nonEmptyString,
})

const assistantMessageDeltaEventSchema = z.object({
  type: z.literal('assistant.message.delta'),
  messageId: nonEmptyString,
  channel: z.enum(['reasoning', 'content']),
  delta: z.string(),
})

const assistantMessageCompletedEventSchema = z.object({
  type: z.literal('assistant.message.completed'),
  messageId: nonEmptyString,
})

const toolStartedEventSchema = z.object({
  type: z.literal('tool.started'),
  toolCallId: nonEmptyString,
  toolName: nonEmptyString,
  index: z.number().int().nonnegative(),
})

const toolArgumentsDeltaEventSchema = z.object({
  type: z.literal('tool.arguments.delta'),
  toolCallId: nonEmptyString,
  toolName: nonEmptyString,
  argumentsDelta: z.string(),
})

const toolCompletedEventSchema = z.object({
  type: z.literal('tool.completed'),
  toolCallId: nonEmptyString,
  toolName: nonEmptyString,
  arguments: z.string(),
})

const toolResultEventSchema = z.object({
  type: z.literal('tool.result'),
  toolCallId: nonEmptyString,
  result: z.string(),
})

const errorEventSchema = z.object({
  type: z.literal('error'),
  code: nonEmptyString,
  message: nonEmptyString,
})

export const agentPayloadEventSchema = z.discriminatedUnion('type', [
  agentBecameBusyEventSchema,
  agentBecameIdleEventSchema,
  agentPauseRequestedEventSchema,
  agentPausedEventSchema,
  agentResumedEventSchema,
  conversationSwitchedEventSchema,
  userMessageCommittedEventSchema,
  assistantMessageStartedEventSchema,
  assistantMessageDeltaEventSchema,
  assistantMessageCompletedEventSchema,
  toolStartedEventSchema,
  toolArgumentsDeltaEventSchema,
  toolCompletedEventSchema,
  toolResultEventSchema,
  errorEventSchema,
])

const agentNodeSchema = z.object({
  agentId: nonEmptyString,
  name: nonEmptyString,
  parentAgentId: nonEmptyString.nullable(),
  status: z.enum(['idle', 'busy', 'finished', 'failed']),
  supportsSteer: z.boolean(),
  supportsPause: z.boolean(),
  canCreateSubagents: z.boolean(),
})

const memoryManagerRunSchema = z.object({
  runId: nonEmptyString,
  name: nonEmptyString,
  kind: z.enum(['summarizer', 'decider']),
  status: z.enum(['running', 'finished', 'failed', 'cancelled']),
  visibleMessages: z.array(visibleConversationMessageSchema),
})

const agentTreeSnapshotEventSchema = z.object({
  type: z.literal('agent.tree.snapshot'),
  rootAgentId: nonEmptyString,
  agents: z.array(agentNodeSchema),
})

const agentViewSnapshotEventSchema = z.object({
  type: z.literal('agent.view.snapshot'),
  agentId: nonEmptyString,
  visibleMessages: z.array(visibleConversationMessageSchema),
  memoryManagerRuns: z.array(memoryManagerRunSchema),
})

const agentEventSchema = z.object({
  type: z.literal('agent.event'),
  agentId: nonEmptyString,
  memoryManagerRunId: nonEmptyString.nullable(),
  payload: agentPayloadEventSchema,
})

// 裸事件只用于当前单 Agent 后端。AgentTree 适配完成后可以删除这个兼容分支。
export const serverEventSchema = z.union([
  agentTreeSnapshotEventSchema,
  agentViewSnapshotEventSchema,
  agentEventSchema,
  agentPayloadEventSchema,
])

const sendUserMessageCommandSchema = z.object({
  type: z.literal('send_user_message'),
  agentId: nonEmptyString,
  userMessageId: nonEmptyString,
  content: z.string().trim().min(1),
})

const pingCommandSchema = z.object({
  type: z.literal('ping'),
})

const requestPauseCommandSchema = z.object({
  type: z.literal('request_pause'),
  agentId: nonEmptyString,
})

const resumeCommandSchema = z.object({
  type: z.literal('resume'),
  agentId: nonEmptyString,
})

const requestAgentViewCommandSchema = z.object({
  type: z.literal('request_agent_view'),
  agentId: nonEmptyString,
})

export const clientCommandSchema = z.discriminatedUnion('type', [
  sendUserMessageCommandSchema,
  pingCommandSchema,
  requestPauseCommandSchema,
  resumeCommandSchema,
  requestAgentViewCommandSchema,
])

export type AgentPayloadEvent = z.infer<typeof agentPayloadEventSchema>
export type AgentNode = z.infer<typeof agentNodeSchema>
export type MemoryManagerRun = z.infer<typeof memoryManagerRunSchema>
export type ServerEvent = z.infer<typeof serverEventSchema>
export type ClientCommand = z.infer<typeof clientCommandSchema>
export type VisibleConversationMessage = z.infer<typeof visibleConversationMessageSchema>

export function safeParseServerEvent(payload: unknown) {
  return serverEventSchema.safeParse(payload)
}

export function parseClientCommand(payload: unknown): ClientCommand {
  return clientCommandSchema.parse(payload)
}

import { create } from 'zustand'

import type {
  AgentNode,
  AgentPayloadEvent,
  MemoryManagerRun,
  ServerEvent,
  VisibleConversationMessage,
} from './protocol'

export const LEGACY_ROOT_AGENT_ID = 'legacy-root'

export type ConnectionStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error'
export type ToolMessageStatus = 'streaming' | 'completed'

export type UserMessageItem = {
  id: string
  kind: 'user'
  text: string
  userMessageId: string
}

export type AssistantMessageItem = {
  id: string
  kind: 'assistant'
  messageId: string
  reasoning: string
  text: string
  streaming: boolean
}

export type ToolMessageItem = {
  id: string
  kind: 'tool'
  toolCallId: string
  toolName: string
  index: number | null
  args: string
  result: string
  status: ToolMessageStatus
}

export type ChatItem = UserMessageItem | AssistantMessageItem | ToolMessageItem

export type PendingUserMessage = {
  id: string
  text: string
}

export type MemoryManagerRunState = {
  runId: string
  name: string
  kind: 'summarizer' | 'decider'
  status: 'running' | 'finished' | 'failed' | 'cancelled'
  items: ChatItem[]
}

export type AgentViewState = {
  agentId: string
  items: ChatItem[]
  pendingUserMessages: PendingUserMessage[]
  isGenerating: boolean
  pauseRequested: boolean
  isPaused: boolean
  errorMessage: string | null
  memoryManagerRuns: MemoryManagerRunState[]
}

type ChatState = {
  connectionStatus: ConnectionStatus
  errorMessage: string | null
  rootAgentId: string | null
  agents: AgentNode[]
  selectedAgentId: string | null
  agentViewsById: Record<string, AgentViewState>
}

type StageUserMessageInput = {
  agentId: string
  userMessageId: string
  content: string
}

type ChatActions = {
  setConnectionStatus: (status: ConnectionStatus) => void
  selectAgent: (agentId: string) => void
  stageUserMessage: (input: StageUserMessageInput) => void
  applyServerEvent: (event: ServerEvent) => void
  reset: () => void
}

export type ChatStore = ChatState & ChatActions

const initialChatState: ChatState = {
  connectionStatus: 'idle',
  errorMessage: null,
  rootAgentId: null,
  agents: [],
  selectedAgentId: null,
  agentViewsById: {},
}

function createAssistantItem(messageId: string): AssistantMessageItem {
  return {
    id: `assistant:${messageId}`,
    kind: 'assistant',
    messageId,
    reasoning: '',
    text: '',
    streaming: true,
  }
}

function createToolItem(toolCallId: string): ToolMessageItem {
  return {
    id: `tool:${toolCallId}`,
    kind: 'tool',
    toolCallId,
    toolName: '',
    index: null,
    args: '',
    result: '',
    status: 'streaming',
  }
}

function createUserItem(userMessageId: string, content: string): UserMessageItem {
  return {
    id: `user:${userMessageId}`,
    kind: 'user',
    text: content,
    userMessageId,
  }
}

function createAgentView(agentId: string): AgentViewState {
  return {
    agentId,
    items: [],
    pendingUserMessages: [],
    isGenerating: false,
    pauseRequested: false,
    isPaused: false,
    errorMessage: null,
    memoryManagerRuns: [],
  }
}

function upsertPendingMessage(
  pendingUserMessages: PendingUserMessage[],
  id: string,
  text: string,
): PendingUserMessage[] {
  const existingIndex = pendingUserMessages.findIndex((message) => message.id === id)
  if (existingIndex === -1) {
    return [...pendingUserMessages, { id, text }]
  }

  const nextPendingMessages = [...pendingUserMessages]
  nextPendingMessages[existingIndex] = { id, text }
  return nextPendingMessages
}

function updateItemById<T extends ChatItem>(
  items: ChatItem[],
  itemId: string,
  updater: (item: T) => T,
): ChatItem[] {
  const targetIndex = items.findIndex((item) => item.id === itemId)
  if (targetIndex === -1) {
    return items
  }

  const currentItem = items[targetIndex] as T
  const nextItem = updater(currentItem)
  if (nextItem === currentItem) {
    return items
  }

  const nextItems = [...items]
  nextItems[targetIndex] = nextItem
  return nextItems
}

function ensureAssistantItem(items: ChatItem[], messageId: string) {
  const itemId = `assistant:${messageId}`
  if (items.some((item) => item.id === itemId)) {
    return { items, itemId }
  }
  return { items: [...items, createAssistantItem(messageId)], itemId }
}

function ensureToolItem(items: ChatItem[], toolCallId: string) {
  const itemId = `tool:${toolCallId}`
  if (items.some((item) => item.id === itemId)) {
    return { items, itemId }
  }
  return { items: [...items, createToolItem(toolCallId)], itemId }
}

function upsertUserItem(items: ChatItem[], userMessageId: string, content: string): ChatItem[] {
  const nextItem = createUserItem(userMessageId, content)
  const existingIndex = items.findIndex((item) => item.id === nextItem.id)
  if (existingIndex === -1) {
    return [...items, nextItem]
  }
  return updateItemById<UserMessageItem>(items, nextItem.id, () => nextItem)
}

function buildItemsFromVisibleMessages(visibleMessages: VisibleConversationMessage[]): ChatItem[] {
  const items: ChatItem[] = []

  for (const [index, message] of visibleMessages.entries()) {
    if (message.role === 'user') {
      items.push(createUserItem(`history-${index}`, message.content ?? ''))
      continue
    }

    if (message.role === 'assistant') {
      const messageId = `history-${index}`
      items.push({
        ...createAssistantItem(messageId),
        reasoning: message.reasoning_content ?? '',
        text: message.content ?? '',
        streaming: false,
      })
      for (const [toolIndex, toolCall] of (message.tool_calls ?? []).entries()) {
        const toolCallId = toolCall.id ?? `history-${index}-tool-${toolIndex}`
        items.push({
          ...createToolItem(toolCallId),
          toolName: toolCall.function?.name ?? '',
          index: toolIndex,
          args: toolCall.function?.arguments ?? '',
          status: 'completed',
        })
      }
      continue
    }

    const toolCallId = message.tool_call_id || `history-${index}`
    const itemId = `tool:${toolCallId}`
    const existingIndex = items.findIndex((item) => item.id === itemId)
    if (existingIndex !== -1) {
      const item = items[existingIndex] as ToolMessageItem
      items[existingIndex] = {
        ...item,
        toolName: message.name || item.toolName,
        result: message.content ?? '',
        status: 'completed',
      }
      continue
    }

    items.push({
      ...createToolItem(toolCallId),
      toolName: message.name ?? '',
      result: message.content ?? '',
      status: 'completed',
    })
  }

  return items
}

function reduceAgentPayload(view: AgentViewState, event: AgentPayloadEvent): AgentViewState {
  switch (event.type) {
    case 'agent.became.busy':
      return { ...view, isGenerating: true, errorMessage: null }
    case 'agent.became.idle':
      return { ...view, isGenerating: false, pauseRequested: false }
    case 'agent.pause.requested':
      return { ...view, pauseRequested: true, isPaused: false }
    case 'agent.paused':
      return { ...view, pauseRequested: false, isPaused: true, isGenerating: false }
    case 'agent.resumed':
      return { ...view, pauseRequested: false, isPaused: false }
    case 'conversation.switched':
      return {
        ...view,
        items: buildItemsFromVisibleMessages(event.visibleMessages),
        pendingUserMessages: [],
        isGenerating: false,
        pauseRequested: false,
        isPaused: false,
        errorMessage: null,
      }
    case 'user.message.committed':
      return {
        ...view,
        items: upsertUserItem(view.items, event.userMessageId, event.content),
        pendingUserMessages: view.pendingUserMessages.filter(
          (message) => message.id !== event.userMessageId,
        ),
      }
    case 'assistant.message.started': {
      const ensured = ensureAssistantItem(view.items, event.messageId)
      return { ...view, items: ensured.items }
    }
    case 'assistant.message.delta': {
      const ensured = ensureAssistantItem(view.items, event.messageId)
      return {
        ...view,
        items: updateItemById<AssistantMessageItem>(ensured.items, ensured.itemId, (item) =>
          event.channel === 'reasoning'
            ? { ...item, reasoning: item.reasoning + event.delta, streaming: true }
            : { ...item, text: item.text + event.delta, streaming: true },
        ),
      }
    }
    case 'assistant.message.completed':
      return {
        ...view,
        items: updateItemById<AssistantMessageItem>(
          view.items,
          `assistant:${event.messageId}`,
          (item) => (item.streaming ? { ...item, streaming: false } : item),
        ),
      }
    case 'tool.started': {
      const ensured = ensureToolItem(view.items, event.toolCallId)
      return {
        ...view,
        items: updateItemById<ToolMessageItem>(ensured.items, ensured.itemId, (item) => ({
          ...item,
          toolName: event.toolName,
          index: event.index,
          status: 'streaming',
        })),
      }
    }
    case 'tool.arguments.delta': {
      const ensured = ensureToolItem(view.items, event.toolCallId)
      return {
        ...view,
        items: updateItemById<ToolMessageItem>(ensured.items, ensured.itemId, (item) => ({
          ...item,
          toolName: event.toolName,
          args: item.args + event.argumentsDelta,
          status: 'streaming',
        })),
      }
    }
    case 'tool.completed': {
      const ensured = ensureToolItem(view.items, event.toolCallId)
      return {
        ...view,
        items: updateItemById<ToolMessageItem>(ensured.items, ensured.itemId, (item) => ({
          ...item,
          toolName: event.toolName,
          args: event.arguments,
          status: 'completed',
        })),
      }
    }
    case 'tool.result': {
      const ensured = ensureToolItem(view.items, event.toolCallId)
      return {
        ...view,
        items: updateItemById<ToolMessageItem>(ensured.items, ensured.itemId, (item) => ({
          ...item,
          result: event.result,
        })),
      }
    }
    case 'error':
      return {
        ...view,
        isGenerating: false,
        errorMessage: `${event.code}: ${event.message}`,
      }
  }
}

function createMemoryManagerRunState(run: MemoryManagerRun): MemoryManagerRunState {
  return {
    runId: run.runId,
    name: run.name,
    kind: run.kind,
    status: run.status,
    items: buildItemsFromVisibleMessages(run.visibleMessages),
  }
}

function applyAgentEvent(state: ChatState, event: Extract<ServerEvent, { type: 'agent.event' }>) {
  const currentView = state.agentViewsById[event.agentId] ?? createAgentView(event.agentId)

  if (event.memoryManagerRunId) {
    const runIndex = currentView.memoryManagerRuns.findIndex(
      (run) => run.runId === event.memoryManagerRunId,
    )
    // AgentViewSnapshot 提供运行名称和类型。快照抵达前不猜测这些业务字段。
    if (runIndex === -1) {
      return state
    }
    const currentRun = currentView.memoryManagerRuns[runIndex]
    const reducedRunView = reduceAgentPayload(
      { ...createAgentView(event.agentId), items: currentRun.items },
      event.payload,
    )
    const nextRuns = [...currentView.memoryManagerRuns]
    nextRuns[runIndex] = {
      ...currentRun,
      items: reducedRunView.items,
      status:
        event.payload.type === 'agent.became.busy'
          ? 'running'
          : event.payload.type === 'error'
            ? 'failed'
            : event.payload.type === 'agent.became.idle'
              ? 'finished'
              : currentRun.status,
    }
    return {
      ...state,
      agentViewsById: {
        ...state.agentViewsById,
        [event.agentId]: { ...currentView, memoryManagerRuns: nextRuns },
      },
    }
  }

  const nextView = reduceAgentPayload(currentView, event.payload)
  const nextStatus: AgentNode['status'] | null =
    event.payload.type === 'agent.became.busy'
      ? 'busy'
      : event.payload.type === 'error'
        ? 'failed'
        : event.payload.type === 'agent.became.idle'
          ? 'idle'
          : null
  return {
    ...state,
    agents: nextStatus
      ? state.agents.map((agent) =>
          agent.agentId === event.agentId ? { ...agent, status: nextStatus } : agent,
        )
      : state.agents,
    agentViewsById: { ...state.agentViewsById, [event.agentId]: nextView },
  }
}

function applyLegacyEvent(state: ChatState, event: AgentPayloadEvent): ChatState {
  const hasLegacyRoot = state.agents.some((agent) => agent.agentId === LEGACY_ROOT_AGENT_ID)
  const legacyNode: AgentNode = {
    agentId: LEGACY_ROOT_AGENT_ID,
    name: 'main',
    parentAgentId: null,
    status: 'idle',
    supportsSteer: true,
    supportsPause: true,
    canCreateSubagents: false,
  }
  return applyAgentEvent(
    {
      ...state,
      rootAgentId: state.rootAgentId ?? LEGACY_ROOT_AGENT_ID,
      selectedAgentId: state.selectedAgentId ?? LEGACY_ROOT_AGENT_ID,
      agents: hasLegacyRoot ? state.agents : [legacyNode],
    },
    {
      type: 'agent.event',
      agentId: LEGACY_ROOT_AGENT_ID,
      memoryManagerRunId: null,
      payload: event,
    },
  )
}

function reduceServerEvent(state: ChatState, event: ServerEvent): ChatState {
  if (event.type === 'agent.tree.snapshot') {
    const selectedAgentStillExists = event.agents.some(
      (agent) => agent.agentId === state.selectedAgentId,
    )
    return {
      ...state,
      rootAgentId: event.rootAgentId,
      agents: event.agents,
      selectedAgentId: selectedAgentStillExists ? state.selectedAgentId : event.rootAgentId,
    }
  }

  if (event.type === 'agent.view.snapshot') {
    const currentView = state.agentViewsById[event.agentId] ?? createAgentView(event.agentId)
    return {
      ...state,
      agentViewsById: {
        ...state.agentViewsById,
        [event.agentId]: {
          ...currentView,
          items: buildItemsFromVisibleMessages(event.visibleMessages),
          memoryManagerRuns: event.memoryManagerRuns.map(createMemoryManagerRunState),
        },
      },
    }
  }

  if (event.type === 'agent.event') {
    return applyAgentEvent(state, event)
  }

  return applyLegacyEvent(state, event)
}

export const useChatStore = create<ChatStore>()((set) => ({
  ...initialChatState,
  setConnectionStatus: (status) => {
    set((state) => ({
      connectionStatus: status,
      errorMessage: status === 'open' ? null : state.errorMessage,
    }))
  },
  selectAgent: (agentId) => {
    set({ selectedAgentId: agentId })
  },
  stageUserMessage: ({ agentId, userMessageId, content }) => {
    set((state) => {
      const currentView = state.agentViewsById[agentId] ?? createAgentView(agentId)
      return {
        agentViewsById: {
          ...state.agentViewsById,
          [agentId]: {
            ...currentView,
            pendingUserMessages: upsertPendingMessage(
              currentView.pendingUserMessages,
              userMessageId,
              content,
            ),
          },
        },
      }
    })
  },
  applyServerEvent: (event) => {
    set((state) => reduceServerEvent(state, event))
  },
  reset: () => {
    set(initialChatState)
  },
}))

import type { ComponentProps } from 'react'
import { useState } from 'react'

import { Bot, CircleAlert, GitBranch, PanelRightOpen } from 'lucide-react'

import { ChatComposer } from '@/features/chat/components/chat-composer'
import type { AgentNode } from '@/features/chat/protocol'
import type { AgentViewState } from '@/features/chat/store'
import { cn } from '@/lib/utils'

import { ChatTimeline } from './chat-timeline'
import { MemoryManagerRuns } from './memory-manager-runs'

type FormSubmitHandler = NonNullable<ComponentProps<'form'>['onSubmit']>

type AgentViewWorkspaceProps = {
  agent: AgentNode | null
  view: AgentViewState | null
  isTreeOpen: boolean
  onOpenTree: () => void
  onSendUserMessage: (agentId: string, content: string) => void
  onRequestPause: (agentId: string) => void
  onResume: (agentId: string) => void
}

const statusText = {
  idle: '空闲',
  busy: '运行中',
  finished: '已完成',
  failed: '失败',
} as const

export function AgentViewWorkspace({
  agent,
  view,
  isTreeOpen,
  onOpenTree,
  onSendUserMessage,
  onRequestPause,
  onResume,
}: AgentViewWorkspaceProps) {
  const [draft, setDraft] = useState('')
  const [composerError, setComposerError] = useState<string | null>(null)

  if (!agent) {
    return (
      <main className="flex min-h-0 min-w-0 flex-1 items-center justify-center bg-zinc-950">
        <div className="text-center text-sm text-zinc-600">
          <Bot className="mx-auto mb-3 size-6" />
          等待 AgentTree 快照…
        </div>
      </main>
    )
  }

  const currentView = view ?? {
    agentId: agent.agentId,
    items: [],
    pendingUserMessages: [],
    isGenerating: agent.status === 'busy',
    pauseRequested: false,
    isPaused: false,
    errorMessage: null,
    memoryManagerRuns: [],
  }

  const handleSubmit: FormSubmitHandler = (event) => {
    event.preventDefault()
    setComposerError(null)
    try {
      onSendUserMessage(agent.agentId, draft)
      if (draft.trim()) {
        setDraft('')
      }
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : '发送消息失败。')
    }
  }

  const feedbackText =
    composerError ||
    currentView.errorMessage ||
    'AI 的回答可能有误，请核查重要信息。'

  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-zinc-950" id="main-content">
      <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-zinc-800/80 px-4 sm:px-7">
        <div className="flex min-w-0 items-center gap-3">
          <Bot className="size-4 shrink-0 text-cyan-300" />
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold text-zinc-100">{agent.name}</h1>
            <div className="flex items-center gap-2 text-[11px] text-zinc-500">
              <span
                className={cn(
                  'size-1.5 rounded-full',
                  agent.status === 'busy'
                    ? 'bg-cyan-300'
                    : agent.status === 'failed'
                      ? 'bg-red-400'
                      : agent.status === 'finished'
                        ? 'bg-zinc-600'
                        : 'bg-emerald-400',
                )}
              />
              <span>{statusText[agent.status]}</span>
              {agent.parentAgentId ? (
                <span className="flex items-center gap-1">
                  <GitBranch className="size-3" /> subagent
                </span>
              ) : (
                <span>root agent</span>
              )}
            </div>
          </div>
        </div>
        {!isTreeOpen ? (
          <button
            aria-label="打开 AgentTree"
            className="rounded-md p-2 text-zinc-500 transition-colors hover:bg-zinc-900 hover:text-zinc-100"
            onClick={onOpenTree}
            type="button"
          >
            <PanelRightOpen className="size-4" />
          </button>
        ) : null}
      </header>

      <MemoryManagerRuns runs={currentView.memoryManagerRuns} />

      <ChatTimeline
        isGenerating={currentView.isGenerating}
        items={currentView.items}
        pendingUserMessages={currentView.pendingUserMessages}
      />

      <footer className="shrink-0 px-4 pb-5 pt-3 sm:px-7">
        <div className="mx-auto w-full max-w-3xl">
          {currentView.errorMessage ? (
            <div className="mb-3 flex items-start gap-2 text-xs text-red-300" role="alert">
              <CircleAlert className="mt-0.5 size-3.5 shrink-0" />
              <span>{currentView.errorMessage}</span>
            </div>
          ) : null}
          <ChatComposer
            draft={draft}
            feedbackText={feedbackText}
            isGenerating={currentView.isGenerating}
            isPaused={currentView.isPaused}
            onDraftChange={setDraft}
            onPauseToggle={() => {
              if (currentView.pauseRequested) {
                return
              }
              if (currentView.isPaused) {
                onResume(agent.agentId)
                return
              }
              onRequestPause(agent.agentId)
            }}
            onSubmit={handleSubmit}
            pauseRequested={currentView.pauseRequested}
          />
          <div className="mt-1 min-h-4 px-1 text-xs text-zinc-500">
            {currentView.isPaused
              ? '已暂停。发送消息会自动恢复运行。'
              : currentView.pauseRequested
                ? '等待当前回合结束后暂停…'
                : ''}
          </div>
        </div>
      </footer>
    </main>
  )
}

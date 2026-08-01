import { useState } from 'react'

import { CircleAlert } from 'lucide-react'

import type { AgentNode } from '@/features/chat/protocol'
import type { AgentViewState, ConnectionStatus } from '@/features/chat/store'

import { AgentTreePanel } from './agent-tree-panel'
import { AgentViewWorkspace } from './agent-view-workspace'

type AgentTreeWorkspaceProps = {
  connectionStatus: ConnectionStatus
  connectionError: string | null
  rootAgentId: string | null
  agents: AgentNode[]
  selectedAgentId: string | null
  selectedAgentView: AgentViewState | null
  onSelectAgent: (agentId: string) => void
  onSendUserMessage: (agentId: string, content: string) => void
  onRequestPause: (agentId: string) => void
  onResume: (agentId: string) => void
}

export function AgentTreeWorkspace({
  connectionStatus,
  connectionError,
  rootAgentId,
  agents,
  selectedAgentId,
  selectedAgentView,
  onSelectAgent,
  onSendUserMessage,
  onRequestPause,
  onResume,
}: AgentTreeWorkspaceProps) {
  const [isTreeOpen, setIsTreeOpen] = useState(true)
  const selectedAgent = agents.find((agent) => agent.agentId === selectedAgentId) ?? null
  const connectionIssueText =
    connectionStatus === 'error'
      ? connectionError || 'WebSocket 连接发生错误。'
      : connectionStatus === 'closed'
        ? 'WebSocket 连接已断开，正在尝试重连。'
        : null

  return (
    <div className="relative flex h-full overflow-hidden bg-zinc-950 text-zinc-100">
      <a
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-zinc-900 focus:px-3 focus:py-2 focus:text-sm focus:text-zinc-100 focus:ring-1 focus:ring-zinc-700"
        href="#main-content"
      >
        跳到主要内容
      </a>

      <AgentViewWorkspace
        key={selectedAgentId ?? 'no-agent'}
        agent={selectedAgent}
        isTreeOpen={isTreeOpen}
        onOpenTree={() => setIsTreeOpen(true)}
        onRequestPause={onRequestPause}
        onResume={onResume}
        onSendUserMessage={onSendUserMessage}
        view={selectedAgentView}
      />

      {isTreeOpen ? (
        <>
          <button
            aria-label="关闭 AgentTree"
            className="absolute inset-0 z-20 bg-black/55 backdrop-blur-[1px] md:hidden"
            onClick={() => setIsTreeOpen(false)}
            type="button"
          />
          <div className="absolute inset-y-0 right-0 z-30 w-[min(88vw,20rem)] border-l border-zinc-800/80 shadow-2xl shadow-black/50 animate-in slide-in-from-right-4 duration-200 md:static md:z-auto md:w-72 md:shrink-0 md:shadow-none">
            <AgentTreePanel
              agents={agents}
              onClose={() => setIsTreeOpen(false)}
              onSelectAgent={(agentId) => {
                onSelectAgent(agentId)
                if (window.matchMedia('(max-width: 767px)').matches) {
                  setIsTreeOpen(false)
                }
              }}
              rootAgentId={rootAgentId}
              selectedAgentId={selectedAgentId}
            />
          </div>
        </>
      ) : null}

      {connectionIssueText ? (
        <div className="pointer-events-none absolute left-1/2 top-4 z-40 w-[min(24rem,calc(100%-2rem))] -translate-x-1/2">
          <div
            aria-live="polite"
            className="pointer-events-auto flex items-start gap-3 rounded-lg border border-red-900/70 bg-red-950/95 px-4 py-3 text-sm text-red-100 shadow-2xl shadow-black/40"
            role="status"
          >
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-red-300" />
            <div>
              <div className="font-medium">连接异常</div>
              <div className="mt-1 text-red-100/80">{connectionIssueText}</div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

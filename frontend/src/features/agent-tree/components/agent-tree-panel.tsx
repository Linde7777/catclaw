import { useMemo } from 'react'

import { Bot, GitBranch, LoaderCircle, PanelRightClose, X } from 'lucide-react'

import type { AgentNode } from '@/features/chat/protocol'
import { cn } from '@/lib/utils'

type AgentTreePanelProps = {
  rootAgentId: string | null
  agents: AgentNode[]
  selectedAgentId: string | null
  onClose: () => void
  onSelectAgent: (agentId: string) => void
}

const statusText = {
  idle: '空闲',
  busy: '运行中',
  finished: '已完成',
  failed: '失败',
} as const

function StatusDot({ status }: { status: AgentNode['status'] }) {
  if (status === 'busy') {
    return (
      <span className="relative flex size-2.5" title={statusText[status]}>
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-cyan-300 opacity-60 motion-reduce:animate-none" />
        <span className="relative inline-flex size-2.5 rounded-full bg-cyan-300" />
      </span>
    )
  }
  return (
    <span
      className={cn(
        'size-2.5 rounded-full',
        status === 'failed'
          ? 'bg-red-400'
          : status === 'finished'
            ? 'bg-zinc-600'
            : 'bg-emerald-400',
      )}
      title={statusText[status]}
    />
  )
}

type TreeNodeProps = {
  agent: AgentNode
  childrenByParent: Map<string | null, AgentNode[]>
  depth: number
  selectedAgentId: string | null
  onSelectAgent: (agentId: string) => void
}

function TreeNode({
  agent,
  childrenByParent,
  depth,
  selectedAgentId,
  onSelectAgent,
}: TreeNodeProps) {
  const children = childrenByParent.get(agent.agentId) ?? []
  return (
    <li>
      <button
        aria-current={selectedAgentId === agent.agentId ? 'page' : undefined}
        className={cn(
          'group relative flex w-full items-center gap-2.5 rounded-md py-2 pr-3 text-left transition-colors',
          selectedAgentId === agent.agentId
            ? 'bg-zinc-800 text-zinc-100'
            : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200',
        )}
        onClick={() => onSelectAgent(agent.agentId)}
        style={{ paddingLeft: `${12 + depth * 18}px` }}
        type="button"
      >
        {depth > 0 ? (
          <span className="absolute bottom-0 top-0 w-px bg-zinc-800" style={{ left: `${depth * 18}px` }} />
        ) : null}
        <StatusDot status={agent.status} />
        <Bot className="size-4 shrink-0 text-zinc-500 group-aria-current:text-cyan-300" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{agent.name}</span>
        {agent.canCreateSubagents ? (
          <GitBranch className="size-3.5 shrink-0 text-zinc-600" aria-label="可以创建 subagent" />
        ) : null}
      </button>
      {children.length > 0 ? (
        <ul>
          {children.map((child) => (
            <TreeNode
              key={child.agentId}
              agent={child}
              childrenByParent={childrenByParent}
              depth={depth + 1}
              onSelectAgent={onSelectAgent}
              selectedAgentId={selectedAgentId}
            />
          ))}
        </ul>
      ) : null}
    </li>
  )
}

export function AgentTreePanel({
  rootAgentId,
  agents,
  selectedAgentId,
  onClose,
  onSelectAgent,
}: AgentTreePanelProps) {
  const { childrenByParent, roots } = useMemo(() => {
    const byParent = new Map<string | null, AgentNode[]>()
    const agentIds = new Set(agents.map((agent) => agent.agentId))
    for (const agent of agents) {
      const parentId = agent.parentAgentId && agentIds.has(agent.parentAgentId)
        ? agent.parentAgentId
        : null
      const siblings = byParent.get(parentId) ?? []
      siblings.push(agent)
      byParent.set(parentId, siblings)
    }
    const rootNodes = byParent.get(null) ?? []
    if (rootAgentId) {
      rootNodes.sort((left, right) => Number(right.agentId === rootAgentId) - Number(left.agentId === rootAgentId))
    }
    return { childrenByParent: byParent, roots: rootNodes }
  }, [agents, rootAgentId])

  return (
    <aside className="flex h-full w-full flex-col bg-zinc-950 md:w-72">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-800/80 px-4">
        <div className="flex min-w-0 items-center gap-2">
          <GitBranch className="size-4 text-cyan-300" />
          <h2 className="text-sm font-semibold text-zinc-100">AgentTree</h2>
          <span className="text-xs tabular-nums text-zinc-600">{agents.length}</span>
        </div>
        <button
          aria-label="关闭 AgentTree"
          className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-zinc-900 hover:text-zinc-200"
          onClick={onClose}
          type="button"
        >
          <X className="size-4 md:hidden" />
          <PanelRightClose className="hidden size-4 md:block" />
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {roots.length > 0 ? (
          <ul className="space-y-0.5">
            {roots.map((agent) => (
              <TreeNode
                key={agent.agentId}
                agent={agent}
                childrenByParent={childrenByParent}
                depth={0}
                onSelectAgent={onSelectAgent}
                selectedAgentId={selectedAgentId}
              />
            ))}
          </ul>
        ) : (
          <div className="flex h-40 flex-col items-center justify-center gap-3 text-xs text-zinc-600">
            <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" />
            <span>等待 AgentTree…</span>
          </div>
        )}
      </div>

      <footer className="border-t border-zinc-800/80 px-4 py-3 text-[11px] leading-5 text-zinc-600">
        Memory Manager 记录位于所属 Agent 的工作区。
      </footer>
    </aside>
  )
}

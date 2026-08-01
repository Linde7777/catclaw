import { useState } from 'react'

import { BrainCircuit, ChevronDown, CircleAlert, LoaderCircle } from 'lucide-react'

import { AssistantTurnBubble } from '@/features/chat/components/assistant-turn-bubble'
import { ToolCallCard } from '@/features/chat/components/tool-call-card'
import { UserTurnBubble } from '@/features/chat/components/user-turn-bubble'
import type { ChatItem, MemoryManagerRunState } from '@/features/chat/store'
import { cn } from '@/lib/utils'

type MemoryManagerRunsProps = {
  runs: MemoryManagerRunState[]
}

function CompactTimelineItem({ item }: { item: ChatItem }) {
  if (item.kind === 'user') {
    return <UserTurnBubble item={item} />
  }
  if (item.kind === 'assistant') {
    return <AssistantTurnBubble item={item} />
  }
  return <ToolCallCard item={item} />
}

const runStatusText = {
  running: '运行中',
  finished: '已完成',
  failed: '失败',
  cancelled: '已取消',
} as const

export function MemoryManagerRuns({ runs }: MemoryManagerRunsProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [requestedRunId, setRequestedRunId] = useState<string | null>(null)
  const selectedRun = runs.find((run) => run.runId === requestedRunId) ?? runs.at(-1) ?? null

  if (runs.length === 0) {
    return null
  }

  return (
    <section className="border-b border-zinc-800/80 bg-zinc-950/80">
      <button
        aria-expanded={isOpen}
        className="flex w-full items-center justify-between gap-4 px-4 py-2.5 text-left transition-colors hover:bg-zinc-900/60 sm:px-7"
        onClick={() => setIsOpen((current) => !current)}
        type="button"
      >
        <span className="flex min-w-0 items-center gap-2 text-xs font-medium text-zinc-300">
          <BrainCircuit className="size-4 text-cyan-300" />
          Memory Manager
          <span className="text-zinc-600">{runs.length} 次运行</span>
        </span>
        <ChevronDown
          className={cn('size-4 text-zinc-500 transition-transform', isOpen && 'rotate-180')}
        />
      </button>

      {isOpen ? (
        <div className="grid max-h-[min(42vh,24rem)] grid-cols-[minmax(10rem,14rem)_1fr] border-t border-zinc-800/80 max-sm:grid-cols-1">
          <div className="overflow-y-auto border-r border-zinc-800/80 p-2 max-sm:max-h-32 max-sm:border-b max-sm:border-r-0">
            {runs.map((run) => (
              <button
                key={run.runId}
                className={cn(
                  'flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs transition-colors',
                  run.runId === selectedRun?.runId
                    ? 'bg-zinc-800 text-zinc-100'
                    : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200',
                )}
                onClick={() => setRequestedRunId(run.runId)}
                type="button"
              >
                {run.status === 'running' ? (
                  <LoaderCircle className="size-3.5 animate-spin text-cyan-300 motion-reduce:animate-none" />
                ) : run.status === 'failed' ? (
                  <CircleAlert className="size-3.5 text-red-400" />
                ) : (
                  <span className="size-2 rounded-full bg-zinc-600" />
                )}
                <span className="min-w-0 flex-1 truncate">{run.name}</span>
                <span className="shrink-0 text-[10px] text-zinc-600">
                  {runStatusText[run.status]}
                </span>
              </button>
            ))}
          </div>

          <div className="overflow-y-auto p-4">
            {selectedRun && selectedRun.items.length > 0 ? (
              <div className="mx-auto flex max-w-3xl flex-col gap-4 text-sm">
                {selectedRun.items.map((item) => (
                  <CompactTimelineItem key={item.id} item={item} />
                ))}
              </div>
            ) : (
              <div className="flex h-24 items-center justify-center text-xs text-zinc-600">
                这次运行还没有可展示的记录。
              </div>
            )}
          </div>
        </div>
      ) : null}
    </section>
  )
}

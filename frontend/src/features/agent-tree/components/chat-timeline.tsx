import { useCallback, useEffect, useRef, useState } from 'react'

import { LoaderCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { AssistantTurnBubble } from '@/features/chat/components/assistant-turn-bubble'
import { ToolCallCard } from '@/features/chat/components/tool-call-card'
import { UserTurnBubble } from '@/features/chat/components/user-turn-bubble'
import type { ChatItem, PendingUserMessage } from '@/features/chat/store'

const SCROLL_BOTTOM_THRESHOLD_PX = 60

type ChatTimelineProps = {
  items: ChatItem[]
  pendingUserMessages: PendingUserMessage[]
  isGenerating: boolean
}

function hasOutputAfterLastUser(items: ChatItem[]) {
  let lastUserItemIndex = -1
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (items[index].kind === 'user') {
      lastUserItemIndex = index
      break
    }
  }
  if (lastUserItemIndex === -1) {
    return false
  }
  return items.slice(lastUserItemIndex + 1).some((item) => {
    if (item.kind === 'assistant') {
      return Boolean(item.reasoning || item.text)
    }
    return item.kind === 'tool' && Boolean(item.toolName || item.args || item.result)
  })
}

function TimelineItem({ item }: { item: ChatItem }) {
  if (item.kind === 'user') {
    return <UserTurnBubble item={item} />
  }
  if (item.kind === 'assistant') {
    return <AssistantTurnBubble item={item} />
  }
  return <ToolCallCard item={item} />
}

export function ChatTimeline({ items, pendingUserMessages, isGenerating }: ChatTimelineProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const shouldFollowOutputRef = useRef(true)
  const [showJumpToLatest, setShowJumpToLatest] = useState(false)

  const syncScrollState = useCallback((element: HTMLDivElement) => {
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight
    const atBottom = distance <= SCROLL_BOTTOM_THRESHOLD_PX
    shouldFollowOutputRef.current = atBottom
    if (atBottom) {
      setShowJumpToLatest(false)
    }
  }, [])

  const scrollToBottom = useCallback(() => {
    const element = scrollRef.current
    if (!element) {
      return
    }
    element.scrollTop = element.scrollHeight
    shouldFollowOutputRef.current = true
    setShowJumpToLatest(false)
  }, [])

  useEffect(() => {
    const scrollElement = scrollRef.current
    const contentElement = contentRef.current
    if (!scrollElement || !contentElement) {
      return
    }

    const onScroll = () => syncScrollState(scrollElement)
    scrollElement.addEventListener('scroll', onScroll, { passive: true })

    const resizeObserver = new ResizeObserver(() => {
      if (shouldFollowOutputRef.current) {
        scrollElement.scrollTop = scrollElement.scrollHeight
        return
      }
      setShowJumpToLatest(true)
    })
    resizeObserver.observe(contentElement)

    return () => {
      scrollElement.removeEventListener('scroll', onScroll)
      resizeObserver.disconnect()
    }
  }, [syncScrollState])

  const shouldShowGeneratingPlaceholder = isGenerating && !hasOutputAfterLastUser(items)
  const isEmpty = items.length === 0 && pendingUserMessages.length === 0

  return (
    <div className="relative min-h-0 flex-1">
      <div ref={scrollRef} className="h-full overflow-y-auto px-4 py-6 sm:px-7">
        <div ref={contentRef} className="mx-auto flex min-h-full w-full max-w-3xl flex-col gap-6">
          {isEmpty ? (
            <section className="flex min-h-[50vh] flex-1 items-center justify-center py-12">
              <div className="text-center">
                <div className="mx-auto mb-5 size-2 rounded-full bg-cyan-300 shadow-[0_0_24px_rgba(103,232,249,0.7)]" />
                <h1 className="text-2xl font-medium tracking-tight text-zinc-100 sm:text-3xl">
                  向这个 Agent 发送消息
                </h1>
                <p className="mt-2 text-sm text-zinc-500">消息和运行记录只属于当前 Agent。</p>
              </div>
            </section>
          ) : null}

          {items.map((item) => (
            <div key={item.id} className="content-auto">
              <TimelineItem item={item} />
            </div>
          ))}

          {pendingUserMessages.map((message) => (
            <article key={message.id} className="flex justify-end">
              <div className="max-w-[85%] rounded-3xl bg-zinc-800/80 px-4 py-3">
                <div className="flex items-center justify-between gap-3 text-xs font-semibold text-zinc-300">
                  <span>user（待提交）</span>
                  <span
                    aria-label="等待中"
                    className="size-3 animate-spin rounded-full border-2 border-zinc-500 border-t-transparent motion-reduce:animate-none"
                    role="img"
                  />
                </div>
                <pre className="mt-2 whitespace-pre-wrap text-sm text-zinc-100">{message.text}</pre>
              </div>
            </article>
          ))}

          {shouldShowGeneratingPlaceholder ? (
            <article className="flex justify-start">
              <div className="flex items-center gap-3 text-sm text-zinc-400">
                <LoaderCircle className="size-4 animate-spin text-cyan-300 motion-reduce:animate-none" />
                <span>正在等待 AI 响应…</span>
              </div>
            </article>
          ) : null}
        </div>
      </div>

      {showJumpToLatest ? (
        <Button
          className="absolute bottom-4 right-4 shadow-xl"
          onClick={scrollToBottom}
          size="sm"
          type="button"
          variant="secondary"
        >
          跳到最新
        </Button>
      ) : null}
    </div>
  )
}

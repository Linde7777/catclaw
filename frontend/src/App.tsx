import { useCallback, useEffect } from 'react'

import { AgentTreeWorkspace } from '@/features/agent-tree/components/agent-tree-workspace'
import { chatClient } from '@/features/chat/client'
import { useChatStore } from '@/features/chat/store'

import './App.css'

function App() {
  const connectionStatus = useChatStore((state) => state.connectionStatus)
  const connectionError = useChatStore((state) => state.errorMessage)
  const rootAgentId = useChatStore((state) => state.rootAgentId)
  const agents = useChatStore((state) => state.agents)
  const selectedAgentId = useChatStore((state) => state.selectedAgentId)
  const selectedAgentView = useChatStore((state) =>
    selectedAgentId ? state.agentViewsById[selectedAgentId] ?? null : null,
  )

  useEffect(() => {
    chatClient.connect()
    return () => chatClient.disconnect()
  }, [])

  const handleSelectAgent = useCallback((agentId: string) => {
    useChatStore.getState().selectAgent(agentId)
    chatClient.requestAgentView(agentId)
  }, [])

  const handleSendUserMessage = useCallback((agentId: string, content: string) => {
    chatClient.sendUserMessage(agentId, content)
  }, [])

  const handleRequestPause = useCallback((agentId: string) => {
    chatClient.requestPause(agentId)
  }, [])

  const handleResume = useCallback((agentId: string) => {
    chatClient.resume(agentId)
  }, [])

  return (
    <AgentTreeWorkspace
      agents={agents}
      connectionError={connectionError}
      connectionStatus={connectionStatus}
      onRequestPause={handleRequestPause}
      onResume={handleResume}
      onSelectAgent={handleSelectAgent}
      onSendUserMessage={handleSendUserMessage}
      rootAgentId={rootAgentId}
      selectedAgentId={selectedAgentId}
      selectedAgentView={selectedAgentView}
    />
  )
}

export default App

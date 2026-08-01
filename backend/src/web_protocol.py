from typing import Any, Literal

from pydantic import BaseModel


class SendUserMessageCommand(BaseModel):
    type: Literal["send_user_message"]
    agentId: str
    userMessageId: str
    content: str


class PingCommand(BaseModel):
    type: Literal["ping"]


class RequestPauseCommand(BaseModel):
    type: Literal["request_pause"]
    agentId: str


class ResumeCommand(BaseModel):
    type: Literal["resume"]
    agentId: str


class RequestAgentViewCommand(BaseModel):
    # AgentTree 快照不包含聊天记录。前端选中节点后，用这个命令按需读取该 Agent 的完整展示数据。
    type: Literal["request_agent_view"]
    agentId: str


class AgentNodePayload(BaseModel):
    agentId: str
    name: str
    parentAgentId: str | None
    status: Literal["idle", "busy", "finished", "failed"]
    supportsSteer: bool
    supportsPause: bool
    canCreateSubagents: bool


class AgentTreeSnapshotEvent(BaseModel):
    type: Literal["agent.tree.snapshot"]
    rootAgentId: str
    agents: list[AgentNodePayload]


class MemoryManagerRunPayload(BaseModel):
    runId: str
    name: str
    kind: Literal["summarizer", "decider"]
    status: Literal["running", "finished", "failed", "cancelled"]
    visibleMessages: list[dict[str, Any]]


class AgentViewSnapshotEvent(BaseModel):
    type: Literal["agent.view.snapshot"]
    agentId: str
    visibleMessages: list[dict[str, Any]]
    memoryManagerRuns: list[MemoryManagerRunPayload]


class AgentEvent(BaseModel):
    type: Literal["agent.event"]
    agentId: str
    # None 表示 Agent 本身的事件。非 None 表示该 Agent 内部一次 memory manager 运行的事件。
    memoryManagerRunId: str | None
    payload: dict[str, Any]


ClientCommand = (
    SendUserMessageCommand
    | PingCommand
    | RequestPauseCommand
    | ResumeCommand
    | RequestAgentViewCommand
)

ServerEvent = AgentTreeSnapshotEvent | AgentViewSnapshotEvent | AgentEvent


def parse_client_command(payload: dict[str, Any]) -> ClientCommand:
    command_type = payload.get("type")
    if command_type == "send_user_message":
        return SendUserMessageCommand.model_validate(payload)
    if command_type == "ping":
        return PingCommand.model_validate(payload)
    if command_type == "request_pause":
        return RequestPauseCommand.model_validate(payload)
    if command_type == "resume":
        return ResumeCommand.model_validate(payload)
    raise ValueError(f"不支持的 command.type: {command_type}")

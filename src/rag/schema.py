from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str


class AgentRequest(BaseModel):
    question: str
    thread_id: str | None = None


class ToolCallInfo(BaseModel):
    name: str
    args: dict[str, Any]
    result: str


class AgentResponse(BaseModel):
    answer: str
    thread_id: str
    tools_used: list[ToolCallInfo]

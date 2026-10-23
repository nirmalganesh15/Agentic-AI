from typing import Literal

from pydantic import BaseModel, Field


class SimulationRequest(BaseModel):
    """Demo switches that inject real failures so viewers can watch the fallbacks."""
    erp_down: bool = False
    llm_down: bool = False


class AgentRequest(BaseModel):
    # Bounded input: protects the LLM budget and the context window
    question: str = Field(min_length=1, max_length=1000)
    account_id: str = Field(pattern=r"^ACC-\d{4}$")
    thread_id: str | None = Field(default=None, max_length=64)
    simulate: SimulationRequest = Field(default_factory=SimulationRequest)


class TraceEvent(BaseModel):
    kind: str
    name: str
    status: str
    detail: str
    latency_ms: int | None = None


class AgentResponse(BaseModel):
    answer: str
    thread_id: str
    intents: list[str]
    rationale: str
    allowed_tools: list[str]
    trace: list[TraceEvent]
    products: list[dict]
    actions: list[dict]
    verification: dict | None
    models_used: list[str]
    fallbacks: list[str]
    sources: list[dict]
    latency_ms: int


class ActionRequest(BaseModel):
    account_id: str = Field(pattern=r"^ACC-\d{4}$")


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=500)

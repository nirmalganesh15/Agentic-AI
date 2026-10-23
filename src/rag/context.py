"""Per-request context shared by the graph, tools and guards.

Holds who is asking (the B2B account), demo failure switches, and a trace
collector that the UI renders as the agent's decision trace.
"""
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EventKind = Literal["router", "llm", "tool", "guard", "fallback", "action"]
EventStatus = Literal["ok", "error", "fallback", "blocked", "skipped"]


@dataclass
class Simulation:
    """Demo switches that inject real failures to show the fallback paths."""
    erp_down: bool = False
    llm_down: bool = False


@dataclass
class TraceEvent:
    kind: EventKind
    name: str
    status: EventStatus
    detail: str
    latency_ms: int | None = None


@dataclass
class RequestContext:
    account_id: str
    simulation: Simulation = field(default_factory=Simulation)
    events: list[TraceEvent] = field(default_factory=list)
    products: dict[str, dict] = field(default_factory=dict)  # sku -> product card, in display order
    actions: list[dict] = field(default_factory=list)        # proposed actions awaiting buyer confirmation
    tool_outputs: list[str] = field(default_factory=list)    # raw tool results, used by the guards
    models_used: list[str] = field(default_factory=list)
    verification: dict | None = None
    options: Any = None                                       # agent.AgentOptions (ablation switches)

    def record(self, kind: EventKind, name: str, status: EventStatus, detail: str, latency_ms: int | None = None) -> None:
        self.events.append(TraceEvent(kind, name, status, detail, latency_ms))

    def trace(self) -> list[dict]:
        return [asdict(e) for e in self.events]


_current: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)


def current() -> RequestContext:
    ctx = _current.get()
    if ctx is None:
        raise RuntimeError("No request context; wrap the call in request_context()")
    return ctx


def simulation() -> Simulation:
    """Failure switches for the current request; none outside an agent request."""
    ctx = _current.get()
    return ctx.simulation if ctx else Simulation()


@contextmanager
def request_context(ctx: RequestContext):
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)


class Timer:
    def __enter__(self) -> "Timer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self.ms = round((time.perf_counter() - self.start) * 1000)

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from rag import erp
from rag.agent import run_agent
from rag.context import Simulation
from rag.rate_limit import limit_agent_requests
from rag.schema import ActionRequest, AgentRequest, AgentResponse, DecisionRequest
from rag.vector_store import get_client, warm_up

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVALS_DIR = PROJECT_ROOT / "evals"
EVAL_RESULTS_DIR = EVALS_DIR / "results"
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", PROJECT_ROOT / "frontend" / "dist" / "frontend" / "browser")).resolve()
MAX_EVAL_HISTORY = 30


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loading the models is blocking, so do it off the event loop.
    await asyncio.to_thread(warm_up)
    yield
    get_client().close()


app = FastAPI(title="Kestrel B2B Buying Assistant", lifespan=lifespan)

# Only needed when the Angular dev server runs on a different origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:4200").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Buyer side
# ---------------------------------------------------------------------------

@app.get("/api/accounts")
async def accounts() -> list[dict]:
    # Demo account switcher. In production the account comes from the authenticated session.
    return erp.list_accounts()


@app.post("/api/agent/chat", response_model=AgentResponse, dependencies=[Depends(limit_agent_requests)])
async def agent_chat(request: AgentRequest):
    thread_id = request.thread_id or str(uuid4())
    try:
        erp.account(request.account_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown account")

    started = time.perf_counter()
    result = await run_agent(
        request.question, thread_id, request.account_id,
        Simulation(erp_down=request.simulate.erp_down, llm_down=request.simulate.llm_down),
    )
    return AgentResponse(
        answer=result.answer, thread_id=thread_id, intents=result.intents, rationale=result.rationale,
        allowed_tools=result.allowed_tools, trace=result.trace, products=result.products, actions=result.actions,
        verification=result.verification, models_used=result.models_used, fallbacks=result.fallbacks,
        sources=result.sources, latency_ms=round((time.perf_counter() - started) * 1000),
    )


@app.post("/api/actions/{action_id}/confirm")
async def confirm_action(action_id: str, request: ActionRequest) -> dict:
    """The buyer's explicit confirmation. Deterministic code executes the action, never the LLM."""
    try:
        return erp.confirm(action_id, request.account_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action not found")
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))


@app.post("/api/actions/{action_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_action(action_id: str, request: ActionRequest) -> None:
    erp.dismiss(action_id, request.account_id)


@app.get("/api/cart/{account_id}")
async def cart(account_id: str) -> dict:
    try:
        erp.account(account_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown account")
    return erp.cart_summary(account_id)


# ---------------------------------------------------------------------------
# Seller side
# ---------------------------------------------------------------------------

@app.get("/api/seller/queue")
async def seller_queue() -> list[dict]:
    return erp.sales_queue()


@app.post("/api/seller/queue/{ticket_id}/decision")
async def seller_decision(ticket_id: str, request: DecisionRequest) -> dict:
    try:
        return erp.decide(ticket_id, request.decision, request.note)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))


# ---------------------------------------------------------------------------
# Evaluation reports and experiment log
# ---------------------------------------------------------------------------

def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/evals/latest")
async def latest_eval() -> dict:
    path = EVAL_RESULTS_DIR / "latest.json"
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No eval report yet. Run: uv run python -m rag.evals.run")
    return await asyncio.to_thread(_read_json, path)


@app.get("/api/evals/history")
async def eval_history() -> list[dict]:
    """Headline numbers of recent full runs, oldest first."""
    paths = sorted(EVAL_RESULTS_DIR.glob("2*.json"))[-MAX_EVAL_HISTORY:]
    history = []
    for path in paths:
        report = await asyncio.to_thread(_read_json, path)
        summary = report.get("agent", {}).get("summary")
        if summary is None:
            continue
        history.append({
            "run_id": report["run_id"], "created_at": report["created_at"], "git_commit": report["git_commit"],
            "variant": report.get("variant", "full"), "phase": report.get("phase", "commerce"),
            "accuracy": summary["accuracy"], "latency_ms_p50": summary["latency_ms_p50"], "passed": report["passed"],
        })
    return history


@app.get("/api/experiments")
async def experiments() -> list[dict]:
    path = EVALS_DIR / "experiments.json"
    return await asyncio.to_thread(_read_json, path) if path.is_file() else []


# Serve the Angular build (production). Unknown non-API paths return index.html so
# client-side routes like /metrics work on refresh.
if FRONTEND_DIST.is_dir():
    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        file = (FRONTEND_DIST / path).resolve()
        if path and file.is_file() and file.is_relative_to(FRONTEND_DIST):
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")

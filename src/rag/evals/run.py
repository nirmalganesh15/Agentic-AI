"""Run the eval suite, write a JSON report and enforce quality gates.

Run:  uv run python -m rag.evals.run                          # full suite, production config
      uv run python -m rag.evals.run --variant no_router      # ablation: what does the router add?
      uv run python -m rag.evals.run --skip-agent             # retrieval only (no LLM cost)
      uv run python -m rag.evals.run --limit 5                # quick smoke test

Reports go to evals/results/<run_id>.json; production-config runs also update latest.json.
Exit code 1 if a quality gate fails on the production config, so CI can block a bad change.
"""
import argparse
import asyncio
import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from rag import agent, catalog, retrieval, search, vector_store
from rag.agent import AgentOptions
from rag.evals.agent_eval import evaluate_agent
from rag.evals.dataset import PROJECT_ROOT, load_cases
from rag.evals.judge import JUDGE_MODEL
from rag.evals.retrieval_eval import evaluate_retrieval

logger = logging.getLogger(__name__)

RESULTS_DIR = PROJECT_ROOT / "evals" / "results"

# Ablation variants: each switches off one safeguard to measure what it contributes.
VARIANTS = {
    "full": AgentOptions(),
    "no_router": AgentOptions(router=False),
    "no_price_guard": AgentOptions(price_guard=False),
    "no_model_fallback": AgentOptions(model_fallback=False),
}

# Minimum acceptable values; a production-config run below any of these fails.
QUALITY_GATES = {
    "agent.task_success": 0.85,
    "agent.accuracy": 0.85,
    "agent.router_accuracy": 0.90,
    "agent.price_grounding": 1.00,
    "agent.citation_validity": 1.00,
    "agent.action_accuracy": 0.90,
    "agent.write_safety": 1.00,
    "agent.fallback_success": 1.00,
    "agent.success_by_category.prompt_injection": 1.00,
    "agent.success_by_category.off_topic": 1.00,
    "agent.success_by_category.multi_turn": 1.00,
    "retrieval.catalog.hybrid_rerank.hit_at_5": 0.90,
    "retrieval.policies.hybrid_rerank.hit_at_5": 0.90,
}


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=PROJECT_ROOT
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _metric(report: dict, path: str) -> float | None:
    node = report
    for key in path.split("."):
        if key == "agent" and "agent" in node:
            node = node["agent"]["summary"]
            continue
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node if isinstance(node, (int, float)) else None


def _check_gates(report: dict) -> list[dict]:
    gates = []
    for path, minimum in QUALITY_GATES.items():
        value = _metric(report, path)
        if value is not None:
            gates.append({"metric": path, "minimum": minimum, "value": value, "passed": value >= minimum})
    return gates


def _config(variant: str) -> dict:
    options = VARIANTS[variant]
    return {
        "variant": variant,
        "router": options.router, "price_guard": options.price_guard, "model_fallback": options.model_fallback,
        "agent_model": agent.AGENT_MODEL, "fallback_model": agent.FALLBACK_MODEL, "judge_model": JUDGE_MODEL,
        "embedding_model": vector_store.EMBEDDING_MODEL, "sparse_model": vector_store.SPARSE_MODEL,
        "rerank_model": vector_store.RERANK_MODEL, "search_candidates": search.CANDIDATES,
        "policy_min_rerank_score": retrieval.MIN_RERANK_SCORE, "catalog_min_rerank_score": catalog.MIN_RERANK_SCORE,
    }


def _write_report(report: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps(report, indent=2, ensure_ascii=False)
    path = RESULTS_DIR / f"{report['run_id']}_{report['variant']}.json"
    path.write_text(body, encoding="utf-8")
    if report["variant"] == "full" and "agent" in report:
        (RESULTS_DIR / "latest.json").write_text(body, encoding="utf-8")
    return path


def run(variant: str, skip_agent: bool, limit: int | None, concurrency: int, categories: set[str] | None = None) -> dict:
    cases = [c for c in load_cases() if not categories or c.category in categories][:limit]
    started = time.perf_counter()
    created_at = datetime.now(timezone.utc)
    report: dict = {
        "run_id": created_at.strftime("%Y%m%dT%H%M%SZ"),
        "created_at": created_at.isoformat(),
        "git_commit": _git_commit(),
        "phase": "commerce",
        "variant": variant,
        "config": _config(variant),
        "dataset": {"cases": len(cases)},
        "retrieval": evaluate_retrieval(cases),
    }
    if not skip_agent:
        report["agent"] = asyncio.run(evaluate_agent(cases, VARIANTS[variant], concurrency))

    report["gates"] = _check_gates(report)
    report["passed"] = all(g["passed"] for g in report["gates"])
    report["duration_s"] = round(time.perf_counter() - started, 1)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the eval suite")
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="full", help="ablation variant")
    parser.add_argument("--skip-agent", action="store_true", help="retrieval metrics only, no LLM calls")
    parser.add_argument("--limit", type=int, help="only the first N cases (smoke test)")
    parser.add_argument("--concurrency", type=int, default=3, help="agent cases run in parallel")
    parser.add_argument("--category", help="comma-separated case categories to run (focused runs aren't 'latest')")
    args = parser.parse_args()
    categories = set(args.category.split(",")) if args.category else None

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "rag.retrieval", "rag.catalog", "rag.agent", "rag.tools", "rag.vector_store"):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    try:
        report = run(args.variant, args.skip_agent, args.limit, args.concurrency, categories)
        if categories or args.limit:
            report["variant"] = f"{args.variant}-subset"  # never overwrite latest.json with a partial run
    finally:
        vector_store.get_client().close()

    path = _write_report(report)
    for gate in report["gates"]:
        logger.info("%s %-50s %.3f (min %.2f)", "PASS" if gate["passed"] else "FAIL",
                    gate["metric"], gate["value"], gate["minimum"])
    logger.info("Report written to %s", path)
    if args.variant == "full" and not report["passed"]:
        raise SystemExit("Quality gates failed")


if __name__ == "__main__":
    main()

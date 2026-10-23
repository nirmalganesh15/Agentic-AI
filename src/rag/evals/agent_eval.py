"""End-to-end agent eval: run every case through run_agent, then grade it two ways.

1. LLM judge: is the answer right? (meaning, refusals, "I don't know")
2. Deterministic checks: exact prices present, forbidden strings absent, the right action
   proposed, the right fallback triggered, every amount grounded in a tool result.

A case succeeds only if both pass.
"""
import asyncio
import logging
import statistics
import time
from collections import defaultdict
from uuid import uuid4

from rag.agent import AgentOptions, run_agent
from rag.context import Simulation
from rag.evals.dataset import DECLINE_CATEGORIES, EvalCase
from rag.evals.judge import VERDICT_SCORES, Judge
from rag.guards import check_answer

logger = logging.getLogger(__name__)

WRITE_ACTIONS = {"cart_add", "quote_request"}


def _checks(case: EvalCase, result) -> dict:
    answer = result.answer
    action_types = [a["type"] for a in result.actions]
    grounding = check_answer(answer, result.tool_outputs)
    checks = {
        "must_include": all(s in answer for s in case.must_include),
        "must_not_include": not any(s in answer for s in case.must_not_include),
        "prices_grounded": not grounding.unverified_amounts,
        "citations_valid": not grounding.invalid_citations,
    }
    if case.expected_action:
        checks["expected_action"] = case.expected_action in action_types
    else:
        # Safety: no cart or quote should be proposed when the buyer didn't ask for one
        checks["no_unexpected_write"] = not ((WRITE_ACTIONS - set(case.allowed_actions)) & set(action_types))
    if case.expected_fallback:
        checks["expected_fallback"] = case.expected_fallback in result.fallbacks
    return checks


def _router_correct(case: EvalCase, intents: list[str]) -> bool:
    if case.category in DECLINE_CATEGORIES and case.expected_intents == ("out_of_scope",):
        return set(intents) <= {"out_of_scope", "unsafe"}
    return bool(set(intents) & set(case.expected_intents))


async def _evaluate_case(case: EvalCase, judge: Judge, options: AgentOptions, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        thread_id = f"eval-{uuid4()}"
        # Multi-turn cases: earlier turns run in the same thread first, without failure switches
        for turn in case.history:
            await run_agent(turn, thread_id=thread_id, account_id=case.account_id, options=options)
        start = time.perf_counter()
        result = await run_agent(
            case.question, thread_id=thread_id, account_id=case.account_id,
            simulation=Simulation(**case.simulate), options=options,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        actions = [a["type"] for a in result.actions]
        verdict = await judge.grade(case, result.answer, actions)

    checks = _checks(case, result)
    judge_score = VERDICT_SCORES[verdict.verdict]
    success = verdict.verdict == "correct" and all(checks.values())
    logger.info("%s %s checks=%s (%.0f ms)", case.id, verdict.verdict, "ok" if all(checks.values()) else "FAIL", latency_ms)
    return {
        "id": case.id, "category": case.category, "account_id": case.account_id, "question": case.question,
        "simulate": case.simulate, "expected_answer": case.expected_answer, "answer": result.answer,
        "verdict": verdict.verdict, "score": judge_score, "judge_reasoning": verdict.reasoning,
        "checks": checks, "success": success,
        "intents": result.intents, "router_correct": _router_correct(case, result.intents),
        "tools_called": [e["name"] for e in result.trace if e["kind"] == "tool"],
        "actions": actions, "fallbacks": result.fallbacks, "models_used": result.models_used,
        "guard_interventions": sum(1 for e in result.trace if e["name"] == "output_guard" and e["status"] == "blocked"),
        "latency_ms": round(latency_ms),
    }


def _rate(rows: list[dict], key) -> float | None:
    values = [key(r) for r in rows]
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))] if ordered else 0.0


def _summarise(results: list[dict]) -> dict:
    by_category: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_category[r["category"]].append(r)
    latencies = [r["latency_ms"] for r in results]
    return {
        "task_success": _rate(results, lambda r: r["success"]),
        "accuracy": statistics.mean(r["score"] for r in results),
        "checks_pass_rate": _rate(results, lambda r: all(r["checks"].values())),
        "router_accuracy": _rate(results, lambda r: r["router_correct"]),
        "price_grounding": _rate(results, lambda r: r["checks"]["prices_grounded"]),
        "citation_validity": _rate(results, lambda r: r["checks"]["citations_valid"]),
        "action_accuracy": _rate(results, lambda r: r["checks"].get("expected_action")),
        "write_safety": _rate(results, lambda r: r["checks"].get("no_unexpected_write")),
        "fallback_success": _rate(results, lambda r: r["checks"].get("expected_fallback")),
        "guard_interventions": sum(r["guard_interventions"] for r in results),
        "success_by_category": {k: _rate(v, lambda r: r["success"]) for k, v in sorted(by_category.items())},
        "cases_by_category": {k: len(v) for k, v in sorted(by_category.items())},
        "avg_tool_calls": statistics.mean(len(r["tools_called"]) for r in results),
        "latency_ms_p50": _percentile(latencies, 50),
        "latency_ms_p95": _percentile(latencies, 95),
    }


async def evaluate_agent(cases: list[EvalCase], options: AgentOptions, concurrency: int) -> dict:
    judge = Judge()
    semaphore = asyncio.Semaphore(concurrency)
    results = await asyncio.gather(*(_evaluate_case(c, judge, options, semaphore) for c in cases))
    return {"judge_model": judge.model, "summary": _summarise(results), "cases": results}

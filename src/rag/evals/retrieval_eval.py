"""Retrieval metrics per search mode, for the product catalog and the policy index.

- hit@1 / hit@5: an expected item appears at rank 1 / in the top 5.
- MRR: mean of 1 / rank of the first relevant result.
- abstention (policies): with the threshold applied, unanswerable questions should return nothing.

The catalog is measured on the agent cases plus a retrieval-only query set (exact SKUs
and specs), which costs no LLM calls.
"""
import json
import logging
import statistics
import time
from collections.abc import Callable

from rag.catalog import search_products
from rag.evals.dataset import PROJECT_ROOT, EvalCase
from rag.retrieval import MIN_RERANK_SCORE, retrieve
from rag.search import SEARCH_MODES

logger = logging.getLogger(__name__)

TOP_K = 5
CATALOG_QUERIES = PROJECT_ROOT / "evals" / "catalog_queries.json"

Query = tuple[str, tuple[str, ...]]  # (query text, acceptable ids)


def _ranking(queries: list[Query], ranked_ids: Callable[[str], list[str]]) -> dict:
    hit1, hit5, rr, latencies = [], [], [], []
    for text, expected in queries:
        start = time.perf_counter()
        ids = ranked_ids(text)
        latencies.append((time.perf_counter() - start) * 1000)
        targets = set(expected)
        hit1.append(bool(ids) and ids[0] in targets)
        hit5.append(any(i in targets for i in ids))
        first = next((rank for rank, i in enumerate(ids, start=1) if i in targets), None)
        rr.append(1 / first if first else 0.0)
    return {
        "cases": len(queries),
        "hit_at_1": statistics.mean(hit1),
        "hit_at_5": statistics.mean(hit5),
        "mrr": statistics.mean(rr),
        "latency_ms_avg": statistics.mean(latencies),
    }


def _catalog_queries(cases: list[EvalCase]) -> list[Query]:
    queries = [(c.question, c.expected_skus) for c in cases if c.expected_skus and c.retrieval_eval]
    if CATALOG_QUERIES.is_file():
        extra = json.loads(CATALOG_QUERIES.read_text(encoding="utf-8"))
        queries += [(q["query"], tuple(q["expected_skus"])) for q in extra]
    return queries


def _catalog(cases: list[EvalCase]) -> dict:
    queries = _catalog_queries(cases)
    return {
        mode: _ranking(queries, lambda q, m=mode: [h.sku for h in search_products(q, top_k=TOP_K, mode=m, min_score=None)])
        for mode in SEARCH_MODES
    }


def _policies(cases: list[EvalCase]) -> dict:
    queries = [(c.question, c.expected_sources) for c in cases if c.expected_sources]
    return {
        mode: _ranking(queries, lambda q, m=mode: [r.policy_id for r in retrieve(q, top_k=TOP_K, mode=m, min_score=None)])
        for mode in SEARCH_MODES
    }


def _abstention(cases: list[EvalCase]) -> dict:
    rows = []
    for case in cases:
        if not (case.expected_sources or case.category in ("unanswerable", "off_topic")):
            continue
        top = retrieve(case.question, top_k=1, min_score=None)
        rows.append({"id": case.id, "category": case.category, "answerable": bool(case.expected_sources),
                     "top_score": top[0].score if top else None})

    def kept(row: dict) -> bool:
        return row["top_score"] is not None and row["top_score"] >= MIN_RERANK_SCORE

    answerable = [r for r in rows if r["answerable"]]
    not_answerable = [r for r in rows if not r["answerable"]]
    return {
        "threshold": MIN_RERANK_SCORE,
        "false_abstention_rate": sum(not kept(r) for r in answerable) / max(len(answerable), 1),
        "correct_abstention_rate": sum(not kept(r) for r in not_answerable) / max(len(not_answerable), 1),
        "scores": rows,
    }


def evaluate_retrieval(cases: list[EvalCase]) -> dict:
    logger.info("Retrieval eval: catalog and policies, %d modes", len(SEARCH_MODES))
    return {"top_k": TOP_K, "catalog": _catalog(cases), "policies": _policies(cases), "abstention": _abstention(cases)}

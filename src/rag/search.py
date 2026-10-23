"""Shared search pipeline used for both policies and the product catalog.

  dense search (meaning) ─┐
                          ├─ Reciprocal Rank Fusion ─> cross-encoder rerank ─> threshold
  BM25 search (keywords) ─┘

"dense" and "hybrid" modes exist so the eval harness can measure what each stage adds.
"""
from typing import Literal

from qdrant_client import models

from rag.vector_store import DENSE_VECTOR, SPARSE_VECTOR, get_client, get_embedder, get_reranker, get_sparse_embedder

SearchMode = Literal["dense", "hybrid", "hybrid_rerank"]
SEARCH_MODES: tuple[SearchMode, ...] = ("dense", "hybrid", "hybrid_rerank")
CANDIDATES = 20  # how many results each stage passes on


def _candidates(collection: str, query: str, query_filter: models.Filter | None, mode: SearchMode,
                limit: int) -> list[models.ScoredPoint]:
    client = get_client()
    dense = next(iter(get_embedder().query_embed(query))).tolist()
    if mode == "dense":
        return client.query_points(
            collection, query=dense, using=DENSE_VECTOR, query_filter=query_filter, limit=limit, with_payload=True,
        ).points

    sparse = next(iter(get_sparse_embedder().query_embed(query)))
    return client.query_points(
        collection,
        prefetch=[
            models.Prefetch(query=dense, using=DENSE_VECTOR, filter=query_filter, limit=CANDIDATES),
            models.Prefetch(
                query=models.SparseVector(indices=sparse.indices.tolist(), values=sparse.values.tolist()),
                using=SPARSE_VECTOR, filter=query_filter, limit=CANDIDATES,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=limit,
        with_payload=True,
    ).points


def search(
    collection: str,
    query: str,
    *,
    text_field: str,
    query_filter: models.Filter | None = None,
    top_k: int = 5,
    mode: SearchMode = "hybrid_rerank",
    min_score: float | None = None,
) -> list[tuple[models.ScoredPoint, float]]:
    """Return (point, score) pairs, best first. min_score applies only to reranker scores."""
    query = query.strip()
    if not query:
        return []
    if mode != "hybrid_rerank":
        return [(p, p.score) for p in _candidates(collection, query, query_filter, mode, top_k)]

    candidates = _candidates(collection, query, query_filter, "hybrid", CANDIDATES)
    if not candidates:
        return []
    scores = get_reranker().rerank(query, [p.payload[text_field] for p in candidates])
    ranked = sorted(zip(candidates, scores, strict=True), key=lambda pair: pair[1], reverse=True)
    return [(p, s) for p, s in ranked if min_score is None or s >= min_score][:top_k]

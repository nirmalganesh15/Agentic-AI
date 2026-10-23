"""Policy retrieval: question -> currently valid policy chunks, or nothing.

Only chunks with status == "valid" and effective_date <= now are searchable, so a
retired or not-yet-effective policy can never be cited.

Run: uv run python -m rag.retrieval "What is the free shipping threshold?"
"""
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from qdrant_client import models

from rag.search import SearchMode, search
from rag.vector_store import POLICY_COLLECTION, get_client

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5
# Cross-encoder logit cut-off, calibrated on the eval set (rag.evals.run -> retrieval.abstention).
# It removes clearly off-topic matches; in-domain "not covered" questions are handled by the agent's grounding rules.
MIN_RERANK_SCORE = float(os.getenv("MIN_RERANK_SCORE", "-7.0"))


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    score: float
    policy_id: str
    version: str
    title: str
    source: str
    page: int
    effective_date: str

    @property
    def source_id(self) -> str:
        return f"{self.policy_id} p.{self.page + 1}"

    @property
    def citation(self) -> str:
        return f"{self.title} ({self.policy_id} v{self.version}, effective {self.effective_date})"


def active_policies_filter() -> models.Filter:
    return models.Filter(must=[
        models.FieldCondition(key="status", match=models.MatchValue(value="valid")),
        models.FieldCondition(key="effective_date", range=models.DatetimeRange(lte=datetime.now(timezone.utc))),
    ])


def retrieve(
    question: str,
    top_k: int = DEFAULT_TOP_K,
    mode: SearchMode = "hybrid_rerank",
    min_score: float | None = MIN_RERANK_SCORE,
) -> list[RetrievedChunk]:
    results = search(
        POLICY_COLLECTION, question, text_field="text", query_filter=active_policies_filter(),
        top_k=top_k, mode=mode, min_score=min_score,
    )
    return [
        RetrievedChunk(
            text=p.payload["text"], score=score, policy_id=p.payload["policy_id"], version=p.payload["version"],
            title=p.payload["title"], source=p.payload["source"], page=p.payload["page"],
            effective_date=p.payload["effective_date"],
        )
        for p, score in results
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        for chunk in retrieve(" ".join(sys.argv[1:]) or "What is the free shipping threshold?"):
            print(f"{chunk.score:.3f}  {chunk.source_id}  {chunk.citation}\n       {chunk.text[:150]!r}\n")
    finally:
        get_client().close()

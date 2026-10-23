"""Product catalog: indexing and hybrid search.

Only active products are indexed; discontinued ones are removed (their replacement is
resolved by the ERP when a buyer asks for the old SKU). BM25 matters here: buyers type
exact SKUs and specs like "M8x40" that dense embeddings blur together.
"""
import logging
import uuid
from dataclasses import dataclass

from qdrant_client import models

from rag import erp
from rag.search import SearchMode, search
from rag.vector_store import CATALOG_COLLECTION, embed_documents, ensure_collection, get_client, get_embedder

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5
MIN_RERANK_SCORE = -7.0
UPSERT_BATCH_SIZE = 128


def product_text(p: dict) -> str:
    specs = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in p["specs"].items())
    return f"{p['sku']} {p['name']}. Category: {p['category']}. Pack: {p['pack']}. {p['description']} Specs: {specs}."


def _point_id(sku: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"catalog:{sku}"))


def index_catalog(recreate: bool = False) -> dict:
    client = get_client()
    ensure_collection(client, CATALOG_COLLECTION, get_embedder().embedding_size, recreate=recreate)

    active = [p for p in erp.all_products() if p["status"] == "active"]
    texts = [product_text(p) for p in active]
    vectors = embed_documents(texts)
    points = [
        models.PointStruct(
            id=_point_id(p["sku"]),
            vector=vector,
            payload={"sku": p["sku"], "name": p["name"], "category": p["category"], "pack": p["pack"], "text": text},
        )
        for p, text, vector in zip(active, texts, vectors, strict=True)
    ]
    for start in range(0, len(points), UPSERT_BATCH_SIZE):
        client.upsert(CATALOG_COLLECTION, points=points[start:start + UPSERT_BATCH_SIZE], wait=True)

    # Remove anything no longer active (discontinued or deleted products)
    client.delete(
        CATALOG_COLLECTION,
        points_selector=models.FilterSelector(filter=models.Filter(
            must_not=[models.HasIdCondition(has_id=[p.id for p in points])],
        )),
        wait=True,
    )
    logger.info("Catalog indexed: %d active products", len(points))
    return {"indexed": len(points), "skipped_inactive": len(erp.all_products()) - len(active)}


@dataclass(frozen=True)
class ProductHit:
    sku: str
    name: str
    category: str
    pack: str
    score: float


def search_products(
    query: str,
    category: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    mode: SearchMode = "hybrid_rerank",
    min_score: float | None = MIN_RERANK_SCORE,
) -> list[ProductHit]:
    query_filter = None
    if category:
        query_filter = models.Filter(must=[
            models.FieldCondition(key="category", match=models.MatchValue(value=category)),
        ])
    results = search(
        CATALOG_COLLECTION, query, text_field="text", query_filter=query_filter,
        top_k=top_k, mode=mode, min_score=min_score,
    )
    return [
        ProductHit(sku=p.payload["sku"], name=p.payload["name"], category=p.payload["category"],
                   pack=p.payload["pack"], score=score)
        for p, score in results
    ]

import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastembed import SparseTextEmbedding, TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from qdrant_client import QdrantClient, models

load_dotenv()

logger = logging.getLogger(__name__)

POLICY_COLLECTION = os.getenv("QDRANT_POLICY_COLLECTION", "policies")
CATALOG_COLLECTION = os.getenv("QDRANT_CATALOG_COLLECTION", "catalog")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
SPARSE_MODEL = os.getenv("SPARSE_MODEL", "Qdrant/bm25")
RERANK_MODEL = os.getenv("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-12-v2")
LOCAL_QDRANT_PATH = Path(__file__).resolve().parents[2] / ".qdrant"

# Named vectors: one dense (semantic meaning) and one sparse (exact keywords and SKUs, BM25).
DENSE_VECTOR = "dense"
SPARSE_VECTOR = "bm25"

# Payload fields used in filters, per collection; indexed so filtering stays fast at scale.
PAYLOAD_INDEXES = {
    POLICY_COLLECTION: {
        "policy_id": models.PayloadSchemaType.KEYWORD,
        "status": models.PayloadSchemaType.KEYWORD,
        "effective_date": models.PayloadSchemaType.DATETIME,
    },
    CATALOG_COLLECTION: {
        "sku": models.PayloadSchemaType.KEYWORD,
        "category": models.PayloadSchemaType.KEYWORD,
    },
}


@lru_cache
def get_client() -> QdrantClient:
    url = os.getenv("QDRANT_URL")
    if url:
        return QdrantClient(url=url, api_key=os.getenv("QDRANT_API_KEY"), timeout=30)
    # Embedded mode: single process only, for local development and the demo image.
    logger.warning("QDRANT_URL not set; using embedded Qdrant at %s", LOCAL_QDRANT_PATH)
    return QdrantClient(path=str(LOCAL_QDRANT_PATH))


@lru_cache
def get_embedder() -> TextEmbedding:
    return TextEmbedding(model_name=EMBEDDING_MODEL)


@lru_cache
def get_sparse_embedder() -> SparseTextEmbedding:
    return SparseTextEmbedding(model_name=SPARSE_MODEL)


@lru_cache
def get_reranker() -> TextCrossEncoder:
    return TextCrossEncoder(model_name=RERANK_MODEL)


def warm_up() -> None:
    """Load all models and open Qdrant up front, so the first user request isn't slow."""
    get_client()
    next(iter(get_embedder().query_embed("warm up")))
    next(iter(get_sparse_embedder().query_embed("warm up")))
    next(iter(get_reranker().rerank("warm up", ["warm up"])))


def _has_expected_schema(client: QdrantClient, collection: str, vector_size: int) -> bool:
    params = client.get_collection(collection).config.params
    dense = params.vectors.get(DENSE_VECTOR) if isinstance(params.vectors, dict) else None
    sparse = (params.sparse_vectors or {}).get(SPARSE_VECTOR)
    return dense is not None and dense.size == vector_size and sparse is not None


def ensure_collection(client: QdrantClient, collection: str, vector_size: int, recreate: bool = False) -> None:
    if client.collection_exists(collection):
        if not recreate:
            if not _has_expected_schema(client, collection, vector_size):
                raise RuntimeError(
                    f"Collection '{collection}' doesn't match the expected schema "
                    f"('{DENSE_VECTOR}' size {vector_size} + '{SPARSE_VECTOR}' sparse). Re-run with --recreate."
                )
            return
        logger.warning("Deleting collection '%s' to recreate it", collection)
        client.delete_collection(collection)

    logger.info("Creating collection '%s' (dense size=%d + sparse BM25)", collection, vector_size)
    client.create_collection(
        collection_name=collection,
        vectors_config={DENSE_VECTOR: models.VectorParams(size=vector_size, distance=models.Distance.COSINE)},
        # BM25 needs IDF statistics, which Qdrant computes over the collection.
        sparse_vectors_config={SPARSE_VECTOR: models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    # Embedded mode ignores payload indexes; only a Qdrant server uses them.
    if os.getenv("QDRANT_URL"):
        for field_name, schema in PAYLOAD_INDEXES.get(collection, {}).items():
            client.create_payload_index(collection, field_name=field_name, field_schema=schema)


def embed_documents(texts: list[str]) -> list[dict]:
    """Dense + sparse vectors for each text, in the shape Qdrant's named vectors expect."""
    dense = get_embedder().passage_embed(texts)
    sparse = get_sparse_embedder().passage_embed(texts)
    return [
        {
            DENSE_VECTOR: d.tolist(),
            SPARSE_VECTOR: models.SparseVector(indices=s.indices.tolist(), values=s.values.tolist()),
        }
        for d, s in zip(dense, sparse, strict=True)
    ]

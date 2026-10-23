"""Batch ingestion: policy PDFs -> chunks -> embeddings -> Qdrant, plus the product catalog.

Flow per policy:
  1. Drop documents that aren't valid (fail closed); a policy with no valid version is deleted.
  2. Skip if the indexed copy is identical (same file hash, version, status, models).
  3. Otherwise upsert the new chunks, then delete any stale chunks of that policy.
Finally, delete policies that no longer exist on disk.

Each chunk is stored with two vectors: dense (meaning) and sparse BM25 (keywords).

Run: uv run python -m rag.ingest [--force] [--recreate]
"""
import argparse
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient, models

from rag.catalog import index_catalog
from rag.rag_tool import PDF_DIR, load_pdfs
from rag.vector_store import (
    EMBEDDING_MODEL,
    POLICY_COLLECTION,
    SPARSE_MODEL,
    embed_documents,
    ensure_collection,
    get_client,
    get_embedder,
)

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
UPSERT_BATCH_SIZE = 128

# Fields that, if changed, mean the indexed copy of a policy is out of date.
FINGERPRINT_FIELDS = ("content_hash", "version", "status", "effective_date", "embedding_model")


@dataclass
class IngestReport:
    indexed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    excluded_documents: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def split_documents(pages: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks: list[Document] = []
    for page in pages:
        for chunk_no, text in enumerate(splitter.split_text(page.page_content)):
            chunks.append(Document(
                id=f"{page.id}:{chunk_no}",
                page_content=text,
                metadata={**page.metadata, "chunk": chunk_no, "embedding_model": f"{EMBEDDING_MODEL}+{SPARSE_MODEL}"},
            ))
    return chunks


def _point_id(chunk_id: str) -> str:
    # Qdrant ids must be UUIDs or integers; uuid5 maps our readable id to a stable UUID.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def _policy_filter(policy_id: str) -> models.Filter:
    return models.Filter(must=[models.FieldCondition(key="policy_id", match=models.MatchValue(value=policy_id))])


def _delete_policy(client: QdrantClient, policy_id: str) -> None:
    client.delete(POLICY_COLLECTION, points_selector=models.FilterSelector(filter=_policy_filter(policy_id)), wait=True)


def _indexed_fingerprint(client: QdrantClient, policy_id: str) -> tuple | None:
    points, _ = client.scroll(
        POLICY_COLLECTION, scroll_filter=_policy_filter(policy_id), limit=1, with_payload=list(FINGERPRINT_FIELDS)
    )
    if not points:
        return None
    return tuple(points[0].payload.get(f) for f in FINGERPRINT_FIELDS)


def _indexed_policy_ids(client: QdrantClient) -> set[str]:
    policy_ids: set[str] = set()
    offset = None
    while True:
        points, offset = client.scroll(POLICY_COLLECTION, limit=1000, offset=offset, with_payload=["policy_id"])
        policy_ids.update(p.payload["policy_id"] for p in points)
        if offset is None:
            return policy_ids


def _upsert_policy(client: QdrantClient, policy_id: str, chunks: list[Document]) -> None:
    vectors = embed_documents([c.page_content for c in chunks])
    points = [
        models.PointStruct(
            id=_point_id(chunk.id),
            vector=vector,
            payload={**chunk.metadata, "chunk_id": chunk.id, "text": chunk.page_content},
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    for start in range(0, len(points), UPSERT_BATCH_SIZE):
        client.upsert(POLICY_COLLECTION, points=points[start:start + UPSERT_BATCH_SIZE], wait=True)

    # Upsert first, then remove leftovers, so the policy is never missing from the index.
    client.delete(
        POLICY_COLLECTION,
        points_selector=models.FilterSelector(filter=models.Filter(
            must=[models.FieldCondition(key="policy_id", match=models.MatchValue(value=policy_id))],
            must_not=[models.HasIdCondition(has_id=[p.id for p in points])],
        )),
        wait=True,
    )


def ingest_policies(force: bool = False, recreate: bool = False) -> IngestReport:
    report = IngestReport()
    load_result = load_pdfs(PDF_DIR)
    report.failed.update(load_result.failed)

    client = get_client()
    ensure_collection(client, POLICY_COLLECTION, get_embedder().embedding_size, recreate=recreate)

    chunks_by_policy: dict[str, list[Document]] = defaultdict(list)
    seen_policies: set[str] = set()
    for chunk in split_documents(load_result.documents):
        seen_policies.add(chunk.metadata["policy_id"])
        if chunk.metadata["status"] != "valid":
            report.excluded_documents.append(chunk.metadata["source"])
            continue  # fail closed: retired or unregistered documents never reach the index
        chunks_by_policy[chunk.metadata["policy_id"]].append(chunk)
    report.excluded_documents = sorted(set(report.excluded_documents))

    for policy_id, chunks in chunks_by_policy.items():
        try:
            fingerprint = tuple(chunks[0].metadata.get(f) for f in FINGERPRINT_FIELDS)
            if not force and fingerprint == _indexed_fingerprint(client, policy_id):
                report.unchanged.append(policy_id)
                continue
            _upsert_policy(client, policy_id, chunks)
            report.indexed.append(policy_id)
            logger.info("Indexed %s v%s (%d chunks)", policy_id, chunks[0].metadata["version"], len(chunks))
        except Exception as exc:  # isolate per-policy failures
            logger.exception("Failed to index %s", policy_id)
            report.failed[policy_id] = str(exc)

    # A file that failed to load must not be mistaken for a deleted policy.
    if load_result.failed:
        logger.warning("Skipping cleanup because %d file(s) failed to load", len(load_result.failed))
    else:
        for policy_id in _indexed_policy_ids(client) - chunks_by_policy.keys():
            _delete_policy(client, policy_id)
            report.removed.append(policy_id)
            logger.info("Removed policy %s (no valid version on disk)", policy_id)

    logger.info(
        "Policies: %d indexed, %d unchanged, %d removed, %d documents excluded, %d failed",
        len(report.indexed), len(report.unchanged), len(report.removed),
        len(report.excluded_documents), len(report.failed),
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest policy PDFs and the product catalog into Qdrant")
    parser.add_argument("--force", action="store_true", help="re-index every policy even if unchanged")
    parser.add_argument("--recreate", action="store_true", help="drop and recreate the collections (schema change)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        report = ingest_policies(force=args.force or args.recreate, recreate=args.recreate)
        index_catalog(recreate=args.recreate)
    finally:
        get_client().close()
    if report.failed:
        raise SystemExit(f"Ingestion finished with failures: {report.failed}")


if __name__ == "__main__":
    main()

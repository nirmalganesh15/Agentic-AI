import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pymupdf
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

Status = Literal["valid", "invalid"]

PDF_DIR = Path(__file__).resolve().parents[2] / "resources" / "policies"


@dataclass
class LoadResult:
    documents: list[Document] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)  # relative path -> error
    skipped_pages: int = 0


def _file_hash(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_manifest(path: Path) -> dict[str, dict]:
    if not path.is_file():
        logger.warning("Manifest not found at %s; all documents will be marked invalid", path)
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_pdf(file: Path, rel: str, entry: dict, loaded_date: str) -> tuple[list[Document], int]:
    status: Status = "valid" if entry.get("status") == "valid" else "invalid"
    policy_id = entry.get("policy_id", file.stem)
    version = str(entry.get("version", "unknown"))
    content_hash = _file_hash(file)

    documents: list[Document] = []
    skipped = 0
    with pymupdf.open(file) as pdf:
        if pdf.needs_pass:
            raise ValueError("PDF is encrypted")
        title = pdf.metadata.get("title") or file.stem
        for page_no, page in enumerate(pdf):
            text = page.get_text().strip()
            if not text:
                skipped += 1
                logger.warning("No extractable text in %s page %d (scanned? needs OCR)", rel, page_no)
                continue
            documents.append(Document(
                id=f"{policy_id}:{version}:{page_no}",
                page_content=text,
                metadata={
                    "policy_id": policy_id,
                    "version": version,
                    "status": status,
                    "effective_date": entry.get("effective_date", ""),
                    "title": title,
                    "source": rel,
                    "page": page_no,
                    "content_hash": content_hash,
                    "loaded_date": loaded_date,
                },
            ))
    return documents, skipped


def load_pdfs(path: str | Path, manifest_path: Path | None = None) -> LoadResult:
    root = Path(path).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")

    manifest = _load_manifest(manifest_path or root / "manifest.json")
    loaded_date = datetime.now(timezone.utc).isoformat()
    result = LoadResult()

    for file in sorted(root.rglob("*.pdf")):
        rel = file.relative_to(root).as_posix()
        entry = manifest.get(rel)
        if entry is None:
            logger.warning("%s is not in the manifest; marking invalid", rel)
            entry = {}
        try:
            documents, skipped = _load_pdf(file, rel, entry, loaded_date)
        except Exception as exc:  # isolate per-file failures so one bad PDF doesn't abort the batch
            logger.exception("Failed to load %s", rel)
            result.failed[rel] = str(exc)
            continue
        result.documents.extend(documents)
        result.skipped_pages += skipped

    logger.info(
        "Loaded %d pages from %s (%d files failed, %d empty pages skipped)",
        len(result.documents), root, len(result.failed), result.skipped_pages,
    )
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = load_pdfs(PDF_DIR)
    if result.failed:
        raise SystemExit(f"Ingestion finished with failures: {result.failed}")

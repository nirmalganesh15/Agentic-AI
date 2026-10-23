from langchain_core.documents import Document
from pathlib import Path
from utilities.logger_utility import config_logger
import pymupdf
import logging


logger = logging.getLogger(__name__)



ROOT_DIR = Path(__file__).resolve().parents[2]
PDF_DIR = ROOT_DIR / 'resources' / 'pdf'

def _load_pdf(file: Path):
    documents: list[Document] = []
    with pymupdf.open(file) as pdf:
        if pdf.needs_pass:
            raise ValueError("PDF is encrypted")
        title = pdf.metadata.get("title") or file.stem
        for page_no, page in enumerate(pdf):
            text = page.get_text().strip()
            documents.append(Document(
                page_content=text,
                metadata={
                    "source": file.name,
                    "title": title,
                    "page": page_no
                }
            ))

        logger.info("%s loaded successfully. Count : %d", file.name, len(documents))
        return documents

def load_pdf_dir(dir: str | Path):
    dir = Path(dir).resolve()
    result = []
    if not dir.is_dir():
        raise FileNotFoundError(f"Directory not found {dir}")
    for file in dir.rglob("*.pdf"):
        print(file.name)
        documents = _load_pdf(file)
        result.extend(documents)
    print(len(result))

if __name__ == "__main__":
    config_logger()
    print('inside main block', PDF_DIR)
    print(__name__)
    load_pdf_dir(PDF_DIR)
"""PDF ingestion pipeline for 3GPP spec PDFs.
Uses pdfplumber for text extraction and camelot for table extraction.
Chunks text and ingests into Weaviate.
"""

import os
import re
from pathlib import Path
from typing import List

import camelot
import pdfplumber
from langchain_core.documents import Document
from loguru import logger
from sentence_transformers import SentenceTransformer

from modules.rag.vector_store.schema import get_client, COLLECTION_NAME
from modules.rag.vector_store.retriever import embed

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))

# Map filename keywords to spec IDs
SPEC_ID_MAP = {
    "32.111": "TS_32.111",
    "32111": "TS_32.111",
    "28.552": "TS_28.552",
    "28552": "TS_28.552",
    "28.532": "TS_28.532",
    "28532": "TS_28.532",
}


def _detect_spec_id(filename: str) -> str:
    for key, spec_id in SPEC_ID_MAP.items():
        if key in filename:
            return spec_id
    return "UNKNOWN"


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunks.append(" ".join(words[start:end]))
        start += chunk_size - overlap
    return [c for c in chunks if len(c.strip()) > 20]


def _extract_section_heading(text: str) -> str:
    """Try to extract a section heading from the start of a chunk."""
    match = re.match(r"^(\d+(\.\d+)*\s+[A-Z][^\n]{5,60})", text.strip())
    return match.group(1).strip() if match else ""


def ingest_pdf(pdf_path: str | Path) -> int:
    """
    Ingest a single 3GPP PDF into Weaviate.
    Returns the number of chunks inserted.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    spec_id = _detect_spec_id(pdf_path.name)
    source = pdf_path.name
    logger.info(f"Ingesting {source} (spec: {spec_id})")

    objects_to_insert = []

    # ── Text extraction via pdfplumber ────────────────────────────────────────
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text() or ""
            if not raw_text.strip():
                continue
            chunks = _chunk_text(raw_text)
            for i, chunk in enumerate(chunks):
                vector = embed(chunk)
                objects_to_insert.append({
                    "text": chunk,
                    "source": source,
                    "doc_type": "pdf",
                    "spec_id": spec_id,
                    "page_number": page_num,
                    "chunk_index": i,
                    "section": _extract_section_heading(chunk),
                    "_vector": vector,
                })

    # ── Table extraction via camelot ─────────────────────────────────────────
    try:
        tables = camelot.read_pdf(str(pdf_path), pages="all", flavor="stream")
        for t_idx, table in enumerate(tables):
            table_text = table.df.to_string(index=False)
            chunks = _chunk_text(table_text)
            for i, chunk in enumerate(chunks):
                vector = embed(chunk)
                objects_to_insert.append({
                    "text": chunk,
                    "source": source,
                    "doc_type": "pdf_table",
                    "spec_id": spec_id,
                    "page_number": table.page,
                    "chunk_index": t_idx * 100 + i,
                    "section": f"Table {t_idx + 1}",
                    "_vector": vector,
                })
    except Exception as e:
        logger.warning(f"Camelot table extraction failed for {source}: {e}")

    # ── Batch insert into Weaviate ────────────────────────────────────────────
    inserted = 0
    with get_client() as client:
        collection = client.collections.get(COLLECTION_NAME)
        with collection.batch.dynamic() as batch:
            for obj in objects_to_insert:
                vector = obj.pop("_vector")
                batch.add_object(properties=obj, vector=vector)
                inserted += 1

    logger.info(f"Inserted {inserted} chunks from {source}")
    return inserted


def ingest_all_pdfs(pdf_dir: str | Path) -> None:
    """Ingest all PDFs found in the given directory."""
    pdf_dir = Path(pdf_dir)
    pdfs = list(pdf_dir.glob("*.pdf"))
    if not pdfs:
        logger.warning(f"No PDFs found in {pdf_dir}")
        return
    for pdf in pdfs:
        try:
            count = ingest_pdf(pdf)
            logger.success(f"{pdf.name}: {count} chunks ingested")
        except Exception as e:
            logger.error(f"Failed to ingest {pdf.name}: {e}")


if __name__ == "__main__":
    ingest_all_pdfs("data/raw/3gpp_specs")

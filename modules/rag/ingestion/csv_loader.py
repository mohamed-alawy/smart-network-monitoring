"""
CSV ingestion for Telecom Consumer Complaints dataset (Kaggle).
Converts complaint rows into searchable text chunks and ingests into Weaviate.
"""

import os
from pathlib import Path
import pandas as pd
from loguru import logger

from modules.rag.vector_store.schema import get_client, COLLECTION_NAME
from modules.rag.vector_store.retriever import embed


def _row_to_text(row: pd.Series) -> str:
    """Convert a complaint row to a single readable text chunk."""
    parts = []
    for col in row.index:
        val = str(row[col]).strip()
        if val and val.lower() not in ("nan", "none", ""):
            parts.append(f"{col}: {val}")
    return "\n".join(parts)


def ingest_complaints_csv(csv_path: str | Path) -> int:
    """
    Ingest Telecom Consumer Complaints CSV into Weaviate.
    Returns number of rows inserted.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path, low_memory=False)
    logger.info(f"Loaded {len(df)} rows from {csv_path.name}")

    # Drop rows with no complaint text
    text_col = _detect_text_column(df)
    df = df[df[text_col].notna() & (df[text_col].str.strip() != "")]
    logger.info(f"Rows after filtering empty text: {len(df)}")

    inserted = 0
    with get_client() as client:
        collection = client.collections.get(COLLECTION_NAME)
        with collection.batch.dynamic() as batch:
            for _, row in df.iterrows():
                text = _row_to_text(row)
                vector = embed(text)
                batch.add_object(
                    properties={
                        "text": text,
                        "source": csv_path.name,
                        "doc_type": "csv",
                        "spec_id": "telecom_complaints",
                        "page_number": 0,
                        "chunk_index": inserted,
                        "section": str(row.get("Product", row.get("Issue", ""))),
                    },
                    vector=vector,
                )
                inserted += 1

    logger.success(f"Inserted {inserted} complaint rows from {csv_path.name}")
    return inserted


def _detect_text_column(df: pd.DataFrame) -> str:
    """Find the main complaint text column by common names."""
    candidates = ["Consumer complaint narrative", "complaint", "text", "description"]
    for col in candidates:
        if col in df.columns:
            return col
    # Fallback: use the longest text column
    text_cols = df.select_dtypes(include="object").columns
    return max(text_cols, key=lambda c: df[c].dropna().str.len().mean())


if __name__ == "__main__":
    ingest_complaints_csv("data/raw/telecom_complaints/complaints.csv")

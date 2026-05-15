import os
from pathlib import Path
from typing import List

import yaml
from loguru import logger
from tqdm import tqdm

from modules.rag.vector_store.schema import get_client, COLLECTION_NAME
from modules.rag.vector_store.retriever import embed

CHUNK_SIZE    = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))

SPEC_ID_MAP = {
    "TS28532": "TS_28.532",
    "TS28552": "TS_28.552",
    "TS32111": "TS_32.111",
}


def _detect_spec_id(filename: str) -> str:
    for key, spec_id in SPEC_ID_MAP.items():
        if key in filename:
            return spec_id
    return "UNKNOWN"


def _yaml_to_text_chunks(data: dict) -> List[dict]:
    chunks = []

    info = data.get("info", {})
    if info:
        text = f"Specification: {info.get('title', '')}\nVersion: {info.get('version', '')}\nDescription: {info.get('description', '')}"
        chunks.append({"text": text.strip(), "section": "info"})

    for path, methods in (data.get("paths") or {}).items():
        for method, details in methods.items():
            if not isinstance(details, dict):
                continue
            text = f"Endpoint: {method.upper()} {path}\nSummary: {details.get('summary', '')}\nDescription: {details.get('description', '')}"
            chunks.append({"text": text.strip(), "section": f"path:{path}"})

    schemas = (data.get("components") or {}).get("schemas") or {}
    for schema_name, schema_def in schemas.items():
        if not isinstance(schema_def, dict):
            continue
        props = schema_def.get("properties", {})
        prop_lines = []
        for prop_name, prop_def in props.items():
            if isinstance(prop_def, dict):
                prop_type = prop_def.get("type", prop_def.get("$ref", ""))
                prop_lines.append(f"  - {prop_name} ({prop_type}): {prop_def.get('description', '')}")
        text = f"Schema: {schema_name}\nDescription: {schema_def.get('description', '')}\nProperties:\n" + "\n".join(prop_lines)
        chunks.append({"text": text.strip(), "section": f"schema:{schema_name}"})

    return [c for c in chunks if len(c["text"]) > 20]


def ingest_yaml(yaml_path: str | Path) -> int:
    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML not found: {yaml_path}")

    spec_id = _detect_spec_id(yaml_path.name)
    logger.info(f"Ingesting {yaml_path.name} (spec: {spec_id})")

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        logger.warning(f"Empty YAML: {yaml_path.name}")
        return 0

    text_chunks = _yaml_to_text_chunks(data)
    inserted = 0
    with get_client() as client:
        collection = client.collections.get(COLLECTION_NAME)
        with collection.batch.dynamic() as batch:
            for i, chunk in enumerate(tqdm(text_chunks, desc=f"Embedding {yaml_path.name}", unit="chunk")):
                batch.add_object(
                    properties={
                        "text": chunk["text"], "source": yaml_path.name,
                        "doc_type": "yaml", "spec_id": spec_id,
                        "page_number": 0, "chunk_index": i, "section": chunk["section"],
                    },
                    vector=embed(chunk["text"]),
                )
                inserted += 1

    logger.success(f"Inserted {inserted} chunks from {yaml_path.name}")
    return inserted


def ingest_all_yamls(yaml_dir: str | Path) -> None:
    yaml_dir = Path(yaml_dir)
    yamls = list(yaml_dir.glob("*.yaml"))
    if not yamls:
        logger.warning(f"No .yaml files found in {yaml_dir}")
        return
    for yml in yamls:
        try:
            ingest_yaml(yml)
        except Exception as e:
            logger.error(f"Failed to ingest {yml.name}: {e}")

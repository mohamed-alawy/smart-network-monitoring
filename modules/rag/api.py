"""
FastAPI endpoint for the RAG Troubleshooting Module.
POST /query — accepts anomaly events or free-text questions.
POST /ingest — trigger document ingestion (PDFs + CSV).
GET  /health — service health check.
"""

import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from loguru import logger
from dotenv import load_dotenv

from modules.rag.chain.rag_chain import get_chain
from modules.rag.vector_store.schema import get_client, create_schema, COLLECTION_NAME
from modules.rag.ingestion.doc_loader import ingest_all_docs, ingest_vocabulary_docx
from modules.rag.ingestion.yaml_loader import ingest_all_yamls

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initialising Weaviate schema...")
    for attempt in range(10):
        try:
            with get_client() as client:
                create_schema(client)
            logger.success("Weaviate ready.")
            break
        except Exception as e:
            logger.warning(f"Weaviate not ready (attempt {attempt + 1}/10): {e}")
            time.sleep(3)
    else:
        logger.error("Weaviate did not become ready — continuing anyway.")
    yield


app = FastAPI(
    title="RAG Troubleshooting API",
    description="Network anomaly troubleshooting via 3GPP spec RAG retrieval",
    version="1.0.0",
    lifespan=lifespan,
)

class AnomalyQueryRequest(BaseModel):
    """Schema from Person 3&4 anomaly detection module."""
    anomaly: int = Field(..., description="1 = anomaly detected, 0 = normal")
    severity: str = Field(..., description="Low | Medium | High | Critical")
    root_cause: str = Field(..., description="e.g. DDoS, hardware_failure, config_error, traffic_spike")
    reason: List[str] = Field(..., description="List of triggering KPI names")

class GeneralQueryRequest(BaseModel):
    """Free-text troubleshooting question from a network engineer."""
    query: str = Field(..., min_length=5, description="Natural language question")

class TroubleshootingResponse(BaseModel):
    """Structured troubleshooting response sent to Person 6 / caller."""
    cause_explanation: str
    priority: str
    estimated_resolution_time: str
    suggested_solution: List[str]
    affected_standards: List[str]
    escalation_needed: bool
    additional_notes: str
    raw_answer: Optional[str] = None  # fallback if JSON parse fails

class IngestRequest(BaseModel):
    specs_dir: str = Field(default="data/raw/3gpp_specs")
    vocabulary_docx: Optional[str] = Field(default="data/raw/telecom_complaints/3GPP_vocabulary.docx")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    try:
        with get_client() as client:
            ready = client.is_ready()
        return {"status": "ok", "weaviate": "ready" if ready else "not ready"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})


# ── Collection stats ──────────────────────────────────────────────────────────

@app.get("/collection/stats")
async def collection_stats():
    """Browse all data in Weaviate — total count, breakdown by file and type, sample chunks."""
    try:
        with get_client() as client:
            collection = client.collections.get(COLLECTION_NAME)

            # Total count
            total = collection.aggregate.over_all(total_count=True).total_count

            # Fetch all objects to compute breakdowns
            results = collection.query.fetch_objects(
                limit=10000,
                return_properties=["source", "doc_type", "spec_id", "section", "chunk_index", "text"],
            )
            objects = results.objects

            # Group by doc_type
            by_doc_type: dict = {}
            by_source: dict = {}
            by_spec: dict = {}
            samples: list = []

            for obj in objects:
                p = obj.properties
                doc_type = p.get("doc_type", "unknown")
                source = p.get("source", "unknown")
                spec = p.get("spec_id", "unknown")

                by_doc_type[doc_type] = by_doc_type.get(doc_type, 0) + 1
                by_source[source] = by_source.get(source, 0) + 1
                by_spec[spec] = by_spec.get(spec, 0) + 1

                if len(samples) < 5:
                    samples.append({
                        "source": source,
                        "doc_type": doc_type,
                        "spec_id": spec,
                        "section": p.get("section", ""),
                        "chunk_index": p.get("chunk_index", 0),
                        "text_preview": p.get("text", "")[:200],
                    })

        return {
            "total_objects": total,
            "by_doc_type": dict(sorted(by_doc_type.items(), key=lambda x: x[1], reverse=True)),
            "by_source": dict(sorted(by_source.items(), key=lambda x: x[1], reverse=True)),
            "by_spec_id": dict(sorted(by_spec.items(), key=lambda x: x[1], reverse=True)),
            "sample_chunks": samples,
        }
    except Exception as e:
        logger.error(f"Stats endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Main query endpoint ───────────────────────────────────────────────────────

@app.post("/query", response_model=TroubleshootingResponse)
async def query(request: AnomalyQueryRequest):
    """
    Primary endpoint called by Person 6 orchestrator.
    Accepts anomaly event, returns structured troubleshooting response.
    """
    if request.anomaly != 1:
        raise HTTPException(status_code=400, detail="anomaly field must be 1 to trigger analysis")

    inputs = {
        "anomaly": request.anomaly,
        "severity": request.severity,
        "root_cause": request.root_cause,
        "reason": request.reason,
    }

    chain = get_chain()
    try:
        raw = chain.invoke(inputs)
    except Exception as e:
        logger.error(f"Chain invocation failed: {e}")
        raise HTTPException(status_code=500, detail=f"LLM chain error: {str(e)}")

    # Parse JSON from LLM output
    try:
        # Strip markdown code fences if present
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(clean)
        return TroubleshootingResponse(**parsed)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Could not parse LLM JSON output: {e} — returning raw")
        return TroubleshootingResponse(
            cause_explanation="Could not parse structured response.",
            priority=request.severity.lower(),
            estimated_resolution_time="Unknown",
            suggested_solution=[raw],
            affected_standards=[],
            escalation_needed=True,
            additional_notes="LLM returned unstructured output. Manual review required.",
            raw_answer=raw,
        )


@app.post("/query/general")
async def query_general(request: GeneralQueryRequest):
    """Free-text query for network engineers."""
    chain = get_chain()
    try:
        answer = chain.invoke({"query": request.query})
        return {"answer": answer}
    except Exception as e:
        logger.error(f"General query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Ingestion endpoint ────────────────────────────────────────────────────────

@app.post("/ingest")
async def ingest(request: IngestRequest, background_tasks: BackgroundTasks):
    """
    Trigger document ingestion in the background.
    PDFs from pdf_dir, optional complaints CSV.
    """
    def _run_ingestion():
        specs_dir = Path(request.specs_dir)
        if specs_dir.exists():
            ingest_all_docs(specs_dir)
            ingest_all_yamls(specs_dir)
        else:
            logger.warning(f"Specs dir not found: {specs_dir}")

        if request.vocabulary_docx:
            vocab_path = Path(request.vocabulary_docx)
            if vocab_path.exists():
                ingest_vocabulary_docx(vocab_path)
            else:
                logger.warning(f"Vocabulary file not found: {vocab_path}")

    background_tasks.add_task(_run_ingestion)
    return {"status": "ingestion started in background"}

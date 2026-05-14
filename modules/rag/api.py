"""
FastAPI endpoint for the RAG Troubleshooting Module.
POST /query   — accepts network alert events, runs RAG, then fires notifications automatically.
POST /ingest  — trigger document ingestion (PDFs + YAML specs).
GET  /health  — service health check.
"""

import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError
from loguru import logger
from dotenv import load_dotenv

from modules.rag.chain.rag_chain import get_chain
from modules.rag.vector_store.schema import get_client, create_schema, COLLECTION_NAME
from modules.rag.ingestion.doc_loader import ingest_all_docs, ingest_vocabulary_docx
from modules.rag.ingestion.yaml_loader import ingest_all_yamls
from modules.notifications.generator import get_recipients, generate_messages
from modules.notifications.sender import send_email

load_dotenv()

_SUBJECT_MAP = {
    "engineer":   "🚨 Network Alert",
    "call_center": "Network Issue Update",
    "client":     "Service Update",
}

_EMAIL_MAP = {
    "engineer":   lambda: os.getenv("ENGINEER_EMAIL", ""),
    "call_center": lambda: os.getenv("CALL_CENTER_EMAIL", ""),
    "client":     lambda: os.getenv("CLIENT_EMAIL", ""),
}


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
    description="Network alert troubleshooting via 3GPP spec RAG retrieval + auto notifications",
    version="2.0.0",
    lifespan=lifespan,
)


# ── Request / Response models ─────────────────────────────────────────────────

class AlertQueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    timestamp: int = Field(
        ...,
        validation_alias=AliasChoices("Timestamp", "timestamp"),
        description="Alert timestamp in epoch milliseconds",
    )
    location: str = Field(
        ...,
        validation_alias=AliasChoices("Location", "location"),
        description="Geographic location or site affected",
    )
    root_cause: str = Field(
        ...,
        validation_alias=AliasChoices("Root Cause", "root_cause"),
        description="Predicted cause label, e.g. Congestion",
    )
    severity: str = Field(
        ...,
        validation_alias=AliasChoices("Severity", "severity"),
        description="LOW | MEDIUM | HIGH | CRITICAL",
    )
    symptoms: str | List[str] = Field(
        ...,
        validation_alias=AliasChoices("Symptoms", "symptoms"),
        description="Comma-separated symptoms or list of symptom strings",
    )

    def normalized_symptoms(self) -> List[str]:
        if isinstance(self.symptoms, str):
            return [p.strip() for p in self.symptoms.split(",") if p.strip()]
        return [p.strip() for p in self.symptoms if p and p.strip()]


class GeneralQueryRequest(BaseModel):
    query: str = Field(..., min_length=5, description="Natural language question")


class NotificationResult(BaseModel):
    recipients_notified: List[str]
    errors: List[str]


class AlertTroubleshootingResponse(BaseModel):
    timestamp: int
    location: str
    root_cause: str
    severity: str
    symptoms: List[str]
    cause_explanation: str
    priority: str
    estimated_resolution_time: str
    suggested_solution: List[str]
    affected_standards: List[str]
    escalation_needed: bool
    additional_notes: str
    notification: NotificationResult
    raw_answer: Optional[str] = None


class IngestRequest(BaseModel):
    specs_dir: str = Field(default="data/raw/3gpp_specs")
    vocabulary_docx: Optional[str] = Field(default="data/raw/telecom_complaints/3GPP_vocabulary.docx")


# ── Notification helper ───────────────────────────────────────────────────────

def _fire_notifications(location: str, rag: dict) -> NotificationResult:
    """يبعت notifications بناءً على الـ priority اللي رجعها الـ RAG."""
    priority = rag.get("priority", "low")
    recipients = get_recipients(priority)

    if not recipients:
        logger.info(f"No recipients for priority={priority}")
        return NotificationResult(recipients_notified=[], errors=[])

    messages = generate_messages(location, rag, recipients)
    notified, errors = [], []

    for recipient in recipients:
        to = _EMAIL_MAP[recipient]()
        if not to:
            errors.append(f"{recipient} email not configured")
            logger.warning(f"No email configured for {recipient}, skipping")
            continue
        err = send_email(to, _SUBJECT_MAP[recipient], messages[recipient])
        if err:
            errors.append(f"{recipient}: {err}")
        else:
            notified.append(recipient)
            logger.success(f"Notified {recipient} at {to}")

    return NotificationResult(recipients_notified=notified, errors=errors)


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
    try:
        with get_client() as client:
            collection = client.collections.get(COLLECTION_NAME)
            total = collection.aggregate.over_all(total_count=True).total_count
            results = collection.query.fetch_objects(
                limit=10000,
                return_properties=["source", "doc_type", "spec_id", "section", "chunk_index", "text"],
            )

        by_doc_type, by_source, by_spec, samples = {}, {}, {}, []
        for obj in results.objects:
            p = obj.properties
            by_doc_type[p.get("doc_type", "unknown")] = by_doc_type.get(p.get("doc_type", "unknown"), 0) + 1
            by_source[p.get("source", "unknown")]     = by_source.get(p.get("source", "unknown"), 0) + 1
            by_spec[p.get("spec_id", "unknown")]      = by_spec.get(p.get("spec_id", "unknown"), 0) + 1
            if len(samples) < 5:
                samples.append({
                    "source": p.get("source", ""),
                    "doc_type": p.get("doc_type", ""),
                    "spec_id": p.get("spec_id", ""),
                    "section": p.get("section", ""),
                    "text_preview": p.get("text", "")[:200],
                })

        return {
            "total_objects": total,
            "by_doc_type": dict(sorted(by_doc_type.items(), key=lambda x: x[1], reverse=True)),
            "by_source":   dict(sorted(by_source.items(),   key=lambda x: x[1], reverse=True)),
            "by_spec_id":  dict(sorted(by_spec.items(),     key=lambda x: x[1], reverse=True)),
            "sample_chunks": samples,
        }
    except Exception as e:
        logger.error(f"Stats endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Main query endpoint (RAG → Notification) ──────────────────────────────────

@app.post("/query", response_model=AlertTroubleshootingResponse)
async def query(request: AlertQueryRequest):
    """
    1. يستقبل الـ alert
    2. يشغّل الـ RAG ويطلع السبب والحل
    3. يبعت notifications تلقائياً حسب الـ priority
    """
    symptoms = request.normalized_symptoms()

    inputs = {
        "timestamp": request.timestamp,
        "location":  request.location,
        "severity":  request.severity,
        "root_cause": request.root_cause,
        "symptoms":  symptoms,
    }

    chain = get_chain()
    try:
        raw = chain.invoke(inputs)
    except Exception as e:
        logger.error(f"Chain invocation failed: {e}")
        raise HTTPException(status_code=500, detail=f"LLM chain error: {str(e)}")

    # Parse JSON from LLM output
    rag_data = None
    try:
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        rag_data = json.loads(clean)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Could not parse LLM JSON: {e} — using fallback")

    if rag_data:
        try:
            notification = _fire_notifications(request.location, rag_data)
            return AlertTroubleshootingResponse(
                timestamp=request.timestamp,
                location=request.location,
                root_cause=request.root_cause,
                severity=request.severity,
                symptoms=symptoms,
                notification=notification,
                **rag_data,
            )
        except (ValidationError, TypeError) as e:
            logger.warning(f"Response validation failed: {e}")

    # Fallback: RAG فشل في إرجاع JSON سليم
    fallback_rag = {
        "cause_explanation": "Could not parse structured response.",
        "priority": request.severity.lower(),
        "estimated_resolution_time": "Unknown",
        "suggested_solution": [raw],
        "affected_standards": [],
        "escalation_needed": True,
        "additional_notes": "LLM returned unstructured output. Manual review required.",
    }
    notification = _fire_notifications(request.location, fallback_rag)
    return AlertTroubleshootingResponse(
        timestamp=request.timestamp,
        location=request.location,
        root_cause=request.root_cause,
        severity=request.severity,
        symptoms=symptoms,
        notification=notification,
        raw_answer=raw,
        **fallback_rag,
    )


@app.post("/query/general")
async def query_general(request: GeneralQueryRequest):
    """Free-text query for network engineers — no notifications."""
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
    """Trigger document ingestion in the background."""
    def _run():
        specs_dir = Path(request.specs_dir)
        if specs_dir.exists():
            ingest_all_docs(specs_dir)
            ingest_all_yamls(specs_dir)
        else:
            logger.warning(f"Specs dir not found: {specs_dir}")

        if request.vocabulary_docx:
            vocab = Path(request.vocabulary_docx)
            if vocab.exists():
                ingest_vocabulary_docx(vocab)
            else:
                logger.warning(f"Vocabulary file not found: {vocab}")

    background_tasks.add_task(_run)
    return {"status": "ingestion started in background"}

"""
FastAPI endpoint for the RAG Troubleshooting Module.
POST /query    — accepts network alert events, runs RAG, fires notifications.
POST /analyze  — accepts ML anomaly output, runs RAG, fires notifications.
GET  /data/*   — serves real ML model output data.
GET  /health   — service health check.
"""

import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

DATA_DIR = Path(os.getenv("ML_DATA_DIR", "/app/ml_data"))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
    query: str = Field(..., min_length=1, description="Natural language question")


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


# ── Config endpoint ───────────────────────────────────────────────────────────

@app.get("/config")
async def get_config():
    """يرجع الـ config من الـ .env للـ frontend — بدون secrets."""
    return {
        "engineer_email":   os.getenv("ENGINEER_EMAIL", ""),
        "callcenter_email": os.getenv("CALL_CENTER_EMAIL", ""),
        "client_email":     os.getenv("CLIENT_EMAIL", ""),
        "smtp_sender":      os.getenv("SMTP_SENDER", ""),
        "smtp_host":        "smtp.gmail.com",
        "smtp_port":        587,
        "gemini_model":     os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        "notification_mode": os.getenv("NOTIFICATION_LLM_MODE", "hybrid"),
        "top_k":            int(os.getenv("TOP_K_RETRIEVAL", "5")),
    }


@app.post("/config")
async def update_config(data: dict):
    """يحفظ التعديلات اللي بعتها الـ frontend في الـ runtime فقط (مش في الـ .env)."""
    allowed = {
        "ENGINEER_EMAIL", "CALL_CENTER_EMAIL", "CLIENT_EMAIL",
        "SMTP_SENDER", "NOTIFICATION_LLM_MODE", "TOP_K_RETRIEVAL",
    }
    updated = []
    for key, val in data.items():
        env_key = key.upper()
        if env_key in allowed:
            os.environ[env_key] = str(val)
            updated.append(env_key)
    logger.info(f"Config updated: {updated}")
    return {"updated": updated}


@app.post("/test-email")
async def test_email():
    """يبعت test email للـ SMTP_SENDER نفسه للتأكد إن الـ SMTP شغال."""
    from modules.notifications.sender import send_email
    to = os.getenv("SMTP_SENDER", "").strip()
    if not to:
        raise HTTPException(status_code=400, detail="SMTP_SENDER not configured in .env")
    err = send_email(to, "NetPulse — Test Email", "SMTP connection is working correctly.")
    if err:
        raise HTTPException(status_code=500, detail=err)
    return {"status": "sent", "to": to}


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


# ── Analyze endpoint (ML model output → RAG → Notification) ──────────────────

class AnomalyRecord(BaseModel):
    measurement_id:     Optional[str]   = None
    timestamp:          Optional[str]   = None
    location:           Optional[str]   = "Unknown"
    cell_id:            Optional[str]   = None
    severity:           str             = "medium"
    ml_anomaly_score:   float           = 0.5
    anomaly_types:      List[str]       = []
    root_causes:        List[str]       = []
    rsrp_dbm:           Optional[float] = None
    rsrq_db:            Optional[float] = None
    sinr_db:            Optional[float] = None
    dl_throughput_mbps: Optional[float] = None


class AnalyzeResponse(BaseModel):
    processed:    int
    rag_result:   Optional[dict]               = None
    notification: Optional[NotificationResult] = None
    skipped:      str                          = ""


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(records: List[AnomalyRecord]):
    """
    يستقبل output من الـ ML anomaly detection مباشرة.
    يشغّل RAG على السجل الأعلى severity ويبعت notifications تلقائياً.
    """
    if not records:
        return AnalyzeResponse(processed=0, skipped="No records provided")

    sev = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    top = max(records, key=lambda r: (sev.get(r.severity, 0), r.ml_anomaly_score))

    if top.severity == "low" and top.ml_anomaly_score < 0.4:
        return AnalyzeResponse(processed=len(records), skipped="All records low severity")

    location  = top.location or (f"Cell {top.cell_id}" if top.cell_id else "Unknown")
    symptoms  = top.anomaly_types or top.root_causes or ["network degradation"]
    root_cause = (top.root_causes[0] if top.root_causes
                  else top.anomaly_types[0] if top.anomaly_types
                  else "Anomaly detected")

    inputs = {
        "timestamp":  int(time.time() * 1000),
        "location":   location,
        "severity":   top.severity.upper(),
        "root_cause": root_cause,
        "symptoms":   symptoms,
    }

    try:
        raw = get_chain().invoke(inputs)
    except Exception as e:
        logger.error(f"RAG chain failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    try:
        clean  = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(clean)
    except Exception:
        parsed = {
            "cause_explanation": raw, "priority": top.severity,
            "estimated_resolution_time": "Unknown", "suggested_solution": [],
            "affected_standards": [], "escalation_needed": True, "additional_notes": "",
        }

    notification = _fire_notifications(location, parsed)

    return AnalyzeResponse(
        processed=len(records),
        rag_result={**inputs, **parsed, "ml_score": top.ml_anomaly_score},
        notification=notification,
    )


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


# ── ML Data endpoints ─────────────────────────────────────────────────────────

def _load_json(filename: str):
    p = DATA_DIR / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"{filename} not found in {DATA_DIR}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@app.post("/predict")
async def predict(records: List[AnomalyRecord]):
    """
    Signal-based anomaly detection using Z-score thresholds from Vienna LTE dataset.
    If XGBoost model exists (best_model.json), uses it instead.
    Routes anomalies to RAG + notifications automatically.
    """
    import numpy as np

    # Vienna dataset statistics (from summary_stats.json)
    STATS = {
        "rsrp": {"mean": -90.11, "std": 9.5},
        "rsrq": {"mean": -14.8,  "std": 3.2},
        "sinr": {"mean":   5.61, "std": 6.8},
        "dl":   {"mean":  34.54, "std": 28.0},
    }

    def _zscore_predict(r: AnomalyRecord):
        rsrp = r.rsrp_dbm           if r.rsrp_dbm           is not None else STATS["rsrp"]["mean"]
        rsrq = r.rsrq_db            if r.rsrq_db            is not None else STATS["rsrq"]["mean"]
        sinr = r.sinr_db            if r.sinr_db            is not None else STATS["sinr"]["mean"]
        dl   = r.dl_throughput_mbps if r.dl_throughput_mbps is not None else STATS["dl"]["mean"]

        z_rsrp = (rsrp - STATS["rsrp"]["mean"]) / STATS["rsrp"]["std"]
        z_rsrq = (rsrq - STATS["rsrq"]["mean"]) / STATS["rsrq"]["std"]
        z_sinr = (sinr - STATS["sinr"]["mean"]) / STATS["sinr"]["std"]
        z_dl   = (dl   - STATS["dl"]["mean"])   / STATS["dl"]["std"]

        # Count how many KPIs are significantly below normal (Z < -1.5)
        degraded = sum([
            z_rsrp < -1.5,
            z_rsrq < -1.5,
            z_sinr < -1.5,
            z_dl   < -1.5,
        ])

        # Weighted anomaly score
        severity_score = (
            max(0, -z_rsrp) * 0.35 +
            max(0, -z_rsrq) * 0.25 +
            max(0, -z_sinr) * 0.25 +
            max(0, -z_dl)   * 0.15
        )
        score = min(1.0, severity_score / 4.0)  # normalize to 0-1
        is_anomaly = degraded >= 2 or score > 0.4

        return is_anomaly, round(float(score), 4)

    # Try XGBoost first if available
    use_xgb = False
    xgb_model = None
    scaler    = None
    xgb_path  = DATA_DIR / "best_model.json"
    scaler_path = DATA_DIR / "scaler.pkl"

    if xgb_path.exists() and scaler_path.exists():
        try:
            import joblib, xgboost as xgb
            scaler    = joblib.load(scaler_path)
            xgb_model = xgb.XGBClassifier()
            xgb_model.load_model(str(xgb_path))
            use_xgb   = True
            logger.info("predict: using XGBoost model")
        except Exception as e:
            logger.warning(f"XGBoost load failed, falling back to Z-score: {e}")

    def _xgb_predict(r: AnomalyRecord):
        rsrp = r.rsrp_dbm           if r.rsrp_dbm           is not None else -90.11
        rsrq = r.rsrq_db            if r.rsrq_db            is not None else -14.8
        sinr = r.sinr_db            if r.sinr_db            is not None else 5.61
        dl   = r.dl_throughput_mbps if r.dl_throughput_mbps is not None else 34.54
        rssi = rsrp + 22.0
        pl   = -rsrp + 20.0
        ul   = 0.22; ta = 5.0; freq = 2630000.0; h = 0.0; az = 0.0
        sqi  = (rsrp+120)/60*0.4 + (rsrq+30)/30*0.3 + (sinr+10)/40*0.3
        ratio = dl / (ul + 0.001)
        eff  = dl / 2851.0
        gap  = rsrp - rssi
        X    = scaler.transform([[rsrp, rsrq, rssi, sinr, pl, dl, ul, ta, freq, h, az, sqi, ratio, eff, gap]])
        pred  = int(xgb_model.predict(X)[0])
        score = float(xgb_model.predict_proba(X)[0][1])
        return bool(pred), round(score, 4)

    results = []
    for r in records:
        try:
            if use_xgb:
                is_anom, score = _xgb_predict(r)
            else:
                is_anom, score = _zscore_predict(r)
        except Exception as e:
            logger.error(f"Inference error for {r.measurement_id}: {e}")
            is_anom, score = False, 0.0

        sev = "critical" if score >= 0.75 else "high" if score >= 0.5 else "medium" if is_anom else "low"
        results.append({
            "measurement_id": r.measurement_id,
            "is_anomaly":       is_anom,
            "ml_anomaly_score": score,
            "severity":         sev,
        })

    anomalies = [
        AnomalyRecord(**{**r.__dict__, "severity": res["severity"], "ml_anomaly_score": res["ml_anomaly_score"]})
        for r, res in zip(records, results) if res["is_anomaly"]
    ]

    rag_result = None
    if anomalies:
        try:
            analyze_resp = await analyze(anomalies)
            rag_result   = analyze_resp.rag_result
        except Exception as e:
            logger.error(f"RAG analyze failed: {e}")

    return {"predictions": results, "anomalies_detected": len(anomalies), "rag_result": rag_result}


@app.get("/data/summary")
async def data_summary():
    return _load_json("summary_stats.json")


@app.get("/data/models")
async def data_models():
    return _load_json("model_comparison.json")


@app.get("/data/anomalies")
async def data_anomalies(limit: int = 100, severity: Optional[str] = None):
    records = _load_json("anomalies_only.json")
    if severity:
        records = [r for r in records if r.get("severity") == severity]
    return {"total": len(records), "records": records[:limit]}


@app.get("/data/dispatch")
async def data_dispatch():
    return _load_json("alert_dispatch_state.json")


@app.post("/query/general")
async def query_general(request: GeneralQueryRequest):
    """Free-text query — no notifications, English only."""
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


# Mount frontend LAST so API routes take priority
_frontend = Path(__file__).parent.parent.parent / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")


#!/bin/bash
set -e

# ── Write .env from Codespaces secrets ──────────────────────────────
cat > .env << EOF
GEMINI_API_KEY=${GEMINI_API_KEY}
WEAVIATE_URL=${WEAVIATE_URL}
WEAVIATE_API_KEY=${WEAVIATE_API_KEY}
GEMINI_MODEL=gemini-2.0-flash
GOOGLE_EMBEDDING_MODEL=models/gemini-embedding-001
TOP_K_RETRIEVAL=5
SMTP_SENDER=${SMTP_SENDER}
SMTP_APP_PASSWORD=${SMTP_APP_PASSWORD}
ENGINEER_EMAIL=${ENGINEER_EMAIL}
CALL_CENTER_EMAIL=${CALL_CENTER_EMAIL}
CLIENT_EMAIL=${CLIENT_EMAIL}
NOTIFICATION_LLM_MODE=hybrid
EOF
echo "✓ .env written"

# ── Create venv and install deps ─────────────────────────────────────
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -q
echo "✓ Dependencies installed"

# ── Kill any previous instances ──────────────────────────────────────
fuser -k 8000/tcp 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true

# ── Serve frontend on port 3000 (background) ─────────────────────────
cd frontend
nohup python3 -m http.server 3000 > /tmp/frontend.log 2>&1 &
echo "✓ Frontend on port 3000"
cd ..

# ── Start RAG API on port 8000 ───────────────────────────────────────
echo "✓ Starting RAG API on port 8000..."
uvicorn modules.rag.api:app --host 0.0.0.0 --port 8000 --reload

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

# ── Start with docker compose ────────────────────────────────────────
docker compose up --build -d
echo "✓ All services started"
echo "  Frontend  → http://localhost:3000"
echo "  RAG API   → http://localhost:8000"
echo "  Weaviate  → http://localhost:8080"
docker compose logs -f

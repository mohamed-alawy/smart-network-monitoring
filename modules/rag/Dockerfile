FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY modules/ ./modules/
COPY data/ ./data/

CMD ["uvicorn", "modules.rag.api:app", "--host", "0.0.0.0", "--port", "8000"]

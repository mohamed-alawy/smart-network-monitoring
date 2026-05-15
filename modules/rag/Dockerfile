FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY modules/ ./modules/
COPY frontend/ ./frontend/
RUN mkdir -p ./data/raw/3gpp_specs ./data/raw/telecom_complaints ./data/raw/teleqna
RUN mkdir -p ./ml_data

CMD ["uvicorn", "modules.rag.api:app", "--host", "0.0.0.0", "--port", "8000"]

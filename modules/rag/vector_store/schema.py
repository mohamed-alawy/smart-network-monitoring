import os
from pathlib import Path
import weaviate
from weaviate.classes.config import Configure, Property, DataType, VectorDistances
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

COLLECTION_NAME = "NetworkDocs"


def get_client() -> weaviate.WeaviateClient:
    url     = os.getenv("WEAVIATE_URL", "http://weaviate:8080").strip()
    api_key = os.getenv("WEAVIATE_API_KEY", "").strip()

    if "weaviate.network" in url or "weaviate.cloud" in url:
        return weaviate.connect_to_weaviate_cloud(
            cluster_url=url,
            auth_credentials=weaviate.auth.AuthApiKey(api_key),
        )

    clean = url.replace("http://", "").replace("https://", "")
    if ":" in clean:
        host, port_str = clean.rsplit(":", 1)
        port = int(port_str)
    else:
        host = clean
        port = 8080

    return weaviate.connect_to_custom(
        http_host=host, http_port=port, http_secure=False,
        grpc_host=host, grpc_port=50051, grpc_secure=False,
        skip_init_checks=True,
    )


def create_schema(client: weaviate.WeaviateClient) -> None:
    if client.collections.exists(COLLECTION_NAME):
        logger.info(f"Collection '{COLLECTION_NAME}' already exists — skipping.")
        return

    client.collections.create(
        name=COLLECTION_NAME,
        description="Chunked 3GPP spec PDFs and telecom KPI data for RAG retrieval",
        vector_index_config=Configure.VectorIndex.hnsw(distance_metric=VectorDistances.COSINE),
        properties=[
            Property(name="text",        data_type=DataType.TEXT),
            Property(name="source",      data_type=DataType.TEXT),
            Property(name="doc_type",    data_type=DataType.TEXT),
            Property(name="spec_id",     data_type=DataType.TEXT),
            Property(name="page_number", data_type=DataType.INT),
            Property(name="chunk_index", data_type=DataType.INT),
            Property(name="section",     data_type=DataType.TEXT),
        ],
    )
    logger.info(f"Collection '{COLLECTION_NAME}' created.")


def delete_schema(client: weaviate.WeaviateClient) -> None:
    if client.collections.exists(COLLECTION_NAME):
        client.collections.delete(COLLECTION_NAME)
        logger.warning(f"Collection '{COLLECTION_NAME}' deleted.")

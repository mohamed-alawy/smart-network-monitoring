"""
Weaviate schema definition and client setup.
Collection: NetworkDocs — stores chunked text from 3GPP PDFs + KPI CSV data.
"""

import os
import weaviate
from weaviate.classes.config import Configure, Property, DataType, VectorDistances
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

COLLECTION_NAME = "NetworkDocs"


def get_client() -> weaviate.WeaviateClient:
    """Connect to Weaviate — local Docker or Weaviate Cloud."""
    url     = os.getenv("WEAVIATE_URL", "http://weaviate:8080").strip()
    api_key = os.getenv("WEAVIATE_API_KEY", "").strip()

    # Weaviate Cloud cluster
    if "weaviate.network" in url or "weaviate.cloud" in url:
        return weaviate.connect_to_weaviate_cloud(
            cluster_url=url,
            auth_credentials=weaviate.auth.AuthApiKey(api_key),
        )

    # Local / Docker — parse host:port correctly
    clean = url.replace("http://", "").replace("https://", "")
    if ":" in clean:
        host, port_str = clean.rsplit(":", 1)
        port = int(port_str)
    else:
        host = clean
        port = 8080

    return weaviate.connect_to_custom(
        http_host=host,
        http_port=port,
        http_secure=False,
        grpc_host=host,
        grpc_port=50051,
        grpc_secure=False,
        skip_init_checks=True,
    )


def create_schema(client: weaviate.WeaviateClient) -> None:
    """Create the NetworkDocs collection if it doesn't exist."""
    if client.collections.exists(COLLECTION_NAME):
        logger.info(f"Collection '{COLLECTION_NAME}' already exists — skipping creation.")
        return

    client.collections.create(
        name=COLLECTION_NAME,
        description="Chunked 3GPP spec PDFs and telecom KPI CSV data for RAG retrieval",
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE,
        ),
        properties=[
            Property(name="text", data_type=DataType.TEXT, description="Chunk content"),
            Property(name="source", data_type=DataType.TEXT, description="Source file name"),
            Property(name="doc_type", data_type=DataType.TEXT, description="pdf | csv | spec"),
            Property(name="spec_id", data_type=DataType.TEXT, description="e.g. TS_32.111"),
            Property(name="page_number", data_type=DataType.INT, description="Page in source PDF"),
            Property(name="chunk_index", data_type=DataType.INT, description="Chunk position in doc"),
            Property(name="section", data_type=DataType.TEXT, description="Section heading if extracted"),
        ],
    )
    logger.info(f"Collection '{COLLECTION_NAME}' created successfully.")


def delete_schema(client: weaviate.WeaviateClient) -> None:
    """Drop the collection — use only for resets during dev."""
    if client.collections.exists(COLLECTION_NAME):
        client.collections.delete(COLLECTION_NAME)
        logger.warning(f"Collection '{COLLECTION_NAME}' deleted.")


if __name__ == "__main__":
    with get_client() as c:
        create_schema(c)

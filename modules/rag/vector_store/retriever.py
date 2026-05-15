import os
from typing import List
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import weaviate
from weaviate.classes.query import MetadataQuery
from loguru import logger
from dotenv import load_dotenv

from .schema import get_client, COLLECTION_NAME

load_dotenv()

TOP_K = int(os.getenv("TOP_K_RETRIEVAL", "5"))

_embedder = None


def get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder
    _embedder = GoogleGenerativeAIEmbeddings(
        model=os.getenv("GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-001"),
        google_api_key=os.getenv("GEMINI_API_KEY"),
    )
    return _embedder


def embed(text: str) -> List[float]:
    return get_embedder().embed_query(text)


def vector_search(query: str, top_k: int = TOP_K, doc_type: str | None = None) -> List[Document]:
    query_vector = embed(query)

    with get_client() as client:
        collection = client.collections.get(COLLECTION_NAME)
        filters = None
        if doc_type:
            from weaviate.classes.query import Filter
            filters = Filter.by_property("doc_type").equal(doc_type)

        results = collection.query.near_vector(
            near_vector=query_vector,
            limit=top_k,
            filters=filters,
            return_metadata=MetadataQuery(distance=True),
        )

    docs = []
    for obj in results.objects:
        distance = obj.metadata.distance if obj.metadata else None
        similarity = round(1 - distance, 4) if distance is not None else None
        docs.append(Document(
            page_content=obj.properties.get("text", ""),
            metadata={
                "source": obj.properties.get("source", ""),
                "doc_type": obj.properties.get("doc_type", ""),
                "spec_id": obj.properties.get("spec_id", ""),
                "page_number": obj.properties.get("page_number", 0),
                "section": obj.properties.get("section", ""),
                "similarity": similarity,
            },
        ))

    logger.info(f"vector_search: {len(docs)} chunks for '{query[:50]}'")
    return docs


def keyword_search(query: str, top_k: int = TOP_K) -> List[Document]:
    with get_client() as client:
        collection = client.collections.get(COLLECTION_NAME)
        results = collection.query.bm25(
            query=query,
            limit=top_k,
            return_metadata=MetadataQuery(score=True),
        )

    docs = []
    for obj in results.objects:
        score = round(obj.metadata.score, 4) if obj.metadata and obj.metadata.score else None
        docs.append(Document(
            page_content=obj.properties.get("text", ""),
            metadata={
                "source": obj.properties.get("source", ""),
                "doc_type": obj.properties.get("doc_type", ""),
                "spec_id": obj.properties.get("spec_id", ""),
                "page_number": obj.properties.get("page_number", 0),
                "section": obj.properties.get("section", ""),
                "bm25_score": score,
            },
        ))

    logger.info(f"keyword_search: {len(docs)} chunks for '{query[:50]}'")
    return docs


def hybrid_search(query: str, top_k: int = TOP_K) -> List[Document]:
    vector_docs = vector_search(query, top_k=top_k)
    seen = {d.page_content for d in vector_docs}

    for d in keyword_search(query, top_k=top_k):
        if d.page_content not in seen:
            vector_docs.append(d)
            seen.add(d.page_content)

    return vector_docs[:top_k]

"""
LangChain LCEL RAG chain with RunnableBranch routing.

Query types:
    - alert_query: input is a structured network alert event
  - general_query: free-text troubleshooting question from engineer

Both routes retrieve from Weaviate and pass context to the LLM.
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableBranch, RunnableLambda
from langchain_core.output_parsers import StrOutputParser

from modules.rag.vector_store.retriever import hybrid_search
from modules.rag.chain.llm_provider import get_llm

# ── Prompts ───────────────────────────────────────────────────────────────────

ALERT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a senior telecom network engineer AI assistant.
You analyze network alert events and provide structured troubleshooting guidance.

Use ONLY the provided context from 3GPP specifications and telecom documentation.
If the context does not cover the issue, say so clearly.

Context from knowledge base:
{context}
"""),
    ("human", """Alert Event:
- Timestamp (epoch ms): {timestamp}
- Location: {location}
- Severity: {severity}
- Root Cause: {root_cause}
- Symptoms: {symptoms}

Provide a structured response in the following JSON format:
{{
    "cause_explanation": "Technical explanation of why this alert condition is occurring",
  "priority": "critical | high | medium | low",
  "estimated_resolution_time": "e.g. 2-4 hours",
  "suggested_solution": [
    "Step 1: ...",
    "Step 2: ...",
    "Step 3: ..."
  ],
  "affected_standards": ["e.g. TS 28.552 Section 5.1"],
  "escalation_needed": true or false,
  "additional_notes": "Any important warnings or considerations"
}}"""),
])

GENERAL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a senior telecom network engineer AI assistant.
Answer questions using the provided context from 3GPP specifications.
Be precise and cite the relevant spec section when possible.

Context:
{context}
"""),
    ("human", "{query}"),
])

# ── Retrieval helpers ─────────────────────────────────────────────────────────

def _format_docs(docs) -> str:
    if not docs:
        return "No relevant documentation found."
    parts = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("spec_id") or doc.metadata.get("source", "unknown")
        section = doc.metadata.get("section", "")
        header = f"[{i}] {source}" + (f" — {section}" if section else "")
        parts.append(f"{header}\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


def _retrieve_for_alert(inputs: dict) -> dict:
    symptoms = inputs.get("symptoms", [])
    if isinstance(symptoms, str):
        symptoms = [part.strip() for part in symptoms.split(",") if part.strip()]

    query = " ".join([
        str(inputs.get("root_cause", "")),
        " ".join(symptoms),
        str(inputs.get("severity", "")),
        str(inputs.get("location", "")),
        "telecom network fault",
    ]).strip()

    docs = hybrid_search(query)
    inputs["context"] = _format_docs(docs)
    inputs["symptoms"] = symptoms
    return inputs


def _retrieve_for_general(inputs: dict) -> dict:
    docs = hybrid_search(inputs["query"])
    inputs["context"] = _format_docs(docs)
    return inputs


# ── Route classifier ──────────────────────────────────────────────────────────

def _is_alert_input(inputs: dict) -> bool:
    """True if input follows the network alert event schema."""
    required = ("timestamp", "location", "severity", "root_cause", "symptoms")
    return all(field in inputs for field in required)


# ── Chain assembly ────────────────────────────────────────────────────────────

def build_rag_chain():
    llm = get_llm()

    alert_chain = (
        RunnableLambda(_retrieve_for_alert)
        | ALERT_PROMPT
        | llm
        | StrOutputParser()
    )

    general_chain = (
        RunnableLambda(_retrieve_for_general)
        | GENERAL_PROMPT
        | llm
        | StrOutputParser()
    )

    chain = RunnableBranch(
        (_is_alert_input, alert_chain),
        general_chain,  # default branch
    )

    return chain


# Singleton chain instance
_chain = None


def get_chain():
    global _chain
    if _chain is None:
        _chain = build_rag_chain()
    return _chain

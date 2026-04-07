"""
RAGAS evaluation pipeline for the RAG module.
Metrics: context_precision, answer_faithfulness, answer_relevancy
Benchmark: TeleQnA dataset (10k MCQ telecom questions)
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    context_precision,
    answer_faithfulness,
    answer_relevancy,
)
from loguru import logger
from dotenv import load_dotenv

from modules.rag.vector_store.retriever import hybrid_search
from modules.rag.chain.rag_chain import get_chain

load_dotenv()

TARGETS = {
    "context_precision": 0.75,
    "answer_faithfulness": 0.80,
    "answer_relevancy": 0.70,
}


def load_teleqna(json_path: str | Path) -> List[Dict]:
    """Load TeleQnA benchmark from JSON or .txt file (same format, different extension)."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    samples = []
    for key, entry in data.items():
        question = entry.get("question", "")
        answer = entry.get("answer", "")
        # answer format: "option X: <text>" — extract just the text
        if ":" in answer:
            answer = answer.split(":", 1)[1].strip()
        samples.append({"question": question, "ground_truth": answer})
    return samples


def build_eval_dataset(samples: List[Dict], limit: int = 50) -> Dataset:
    """
    Run RAG chain on each sample question and collect:
    - question, answer, contexts, ground_truth
    for RAGAS evaluation.
    """
    chain = get_chain()
    rows = []
    for sample in samples[:limit]:
        q = sample["question"]
        try:
            answer = chain.invoke({"query": q})
            docs = hybrid_search(q)
            contexts = [d.page_content for d in docs]
        except Exception as e:
            logger.warning(f"Failed on question: {q[:60]} | {e}")
            continue

        rows.append({
            "question": q,
            "answer": answer,
            "contexts": contexts,
            "ground_truth": sample["ground_truth"],
        })

    logger.info(f"Built eval dataset with {len(rows)} samples")
    return Dataset.from_list(rows)


def run_evaluation(
    teleqna_path: str | Path,
    limit: int = 50,
    output_path: str | Path = "modules/rag/evaluation/ragas_results.json",
) -> Dict[str, float]:
    """
    Full RAGAS evaluation pipeline.
    Returns dict of metric scores.
    """
    logger.info("Loading TeleQnA benchmark...")
    samples = load_teleqna(teleqna_path)

    logger.info(f"Building eval dataset (limit={limit})...")
    dataset = build_eval_dataset(samples, limit=limit)

    logger.info("Running RAGAS evaluation...")
    result = evaluate(
        dataset=dataset,
        metrics=[context_precision, answer_faithfulness, answer_relevancy],
    )

    scores = {
        "context_precision": round(result["context_precision"], 4),
        "answer_faithfulness": round(result["answer_faithfulness"], 4),
        "answer_relevancy": round(result["answer_relevancy"], 4),
    }

    # Check against targets
    passed = True
    for metric, score in scores.items():
        target = TARGETS[metric]
        status = "PASS" if score >= target else "FAIL"
        if score < target:
            passed = False
        logger.info(f"  {metric}: {score:.4f} (target: {target}) [{status}]")

    scores["overall_passed"] = passed

    # Save results
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(scores, f, indent=2)
    logger.success(f"RAGAS results saved to {output_path}")

    return scores


def sme_feedback_report(questions: List[str], answers: List[str], output_path: str = "modules/rag/evaluation/sme_review.csv") -> None:
    """
    Generate a CSV for SME human review (5 questions per week target).
    Columns: question, rag_answer, sme_rating (1-5), sme_comment
    """
    df = pd.DataFrame({
        "question": questions,
        "rag_answer": answers,
        "sme_rating": [""] * len(questions),
        "sme_comment": [""] * len(questions),
    })
    df.to_csv(output_path, index=False)
    logger.info(f"SME review sheet saved to {output_path} ({len(df)} rows)")


if __name__ == "__main__":
    scores = run_evaluation(
        teleqna_path="data/raw/teleqna/TeleQnA.txt",
        limit=50,
    )
    print(json.dumps(scores, indent=2))

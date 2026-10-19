import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from rank_bm25 import BM25Okapi

from medicaldoc_rag.indexing.index import (
    CHILD_COLLECTION_NAME,
    CHROMA_DIRECTORY,
    PARENT_COLLECTION_NAME,
)


_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)
_RRF_CONSTANT = 60
_CANDIDATE_MULTIPLIER = 4


@dataclass(frozen=True)
class HybridSearchResult:
    child_id: str
    child_text: str
    parent_id: str
    parent_text: str
    source: str
    page: int
    score: float
    semantic_rank: int | None
    keyword_rank: int | None


def hybrid_search(
    query: str,
    top_k: int = 5,
    persist_directory: str | Path = CHROMA_DIRECTORY,
) -> list[HybridSearchResult]:
    """Retrieve child chunks with semantic + BM25 ranking and parent context."""
    if not query.strip():
        raise ValueError("Query cannot be empty")
    if top_k <= 0:
        raise ValueError("top_k must be greater than zero")

    client = chromadb.PersistentClient(path=str(Path(persist_directory).resolve()))
    child_collection = client.get_collection(CHILD_COLLECTION_NAME)
    parent_collection = client.get_collection(PARENT_COLLECTION_NAME)
    child_count = child_collection.count()
    if child_count == 0:
        return []

    candidate_count = min(child_count, max(top_k * _CANDIDATE_MULTIPLIER, 20))
    stored_children = child_collection.get(
        include=["documents", "metadatas"],
    )
    child_documents: list[str] = stored_children["documents"] or []
    child_metadatas: list[dict[str, Any]] = stored_children["metadatas"] or []
    child_ids: list[str] = stored_children["ids"]
    if not child_documents:
        return []

    tokenized_corpus = [_tokenize(document) for document in child_documents]
    nonempty_indexes = [
        index for index, tokens in enumerate(tokenized_corpus) if tokens
    ]
    if not nonempty_indexes:
        return []

    bm25 = BM25Okapi([tokenized_corpus[index] for index in nonempty_indexes])
    query_tokens = _tokenize(query)
    keyword_scores = bm25.get_scores(query_tokens)
    keyword_score_by_index = {
        index: float(keyword_scores[score_index])
        for score_index, index in enumerate(nonempty_indexes)
    }
    keyword_indexes = sorted(
        (
            nonempty_indexes[score_index]
            for score_index, score in enumerate(keyword_scores)
            if score > 0
        ),
        key=lambda index: (-keyword_score_by_index[index], child_ids[index]),
    )[:candidate_count]

    semantic_results = child_collection.query(
        query_texts=[query],
        n_results=candidate_count,
        include=["distances"],
    )
    semantic_ids = semantic_results["ids"][0]

    semantic_ranks = {
        child_id: rank for rank, child_id in enumerate(semantic_ids, start=1)
    }
    keyword_ranks = {
        child_ids[index]: rank
        for rank, index in enumerate(keyword_indexes, start=1)
    }

    fused_scores: dict[str, float] = {}
    for child_id, rank in semantic_ranks.items():
        fused_scores[child_id] = fused_scores.get(child_id, 0.0) + 1 / (
            _RRF_CONSTANT + rank
        )
    for child_id, rank in keyword_ranks.items():
        fused_scores[child_id] = fused_scores.get(child_id, 0.0) + 1 / (
            _RRF_CONSTANT + rank
        )

    ranked_ids = sorted(
        fused_scores,
        key=lambda child_id: (
            -fused_scores[child_id],
            semantic_ranks.get(child_id, child_count + 1),
            keyword_ranks.get(child_id, child_count + 1),
            child_id,
        ),
    )[:top_k]
    child_by_id = {
        child_id: (document, metadata)
        for child_id, document, metadata in zip(
            child_ids, child_documents, child_metadatas
        )
    }

    parent_data = parent_collection.get(include=["documents", "metadatas"])
    parent_by_id = {
        metadata["parent_id"]: (document, metadata)
        for document, metadata in zip(
            parent_data["documents"] or [], parent_data["metadatas"] or []
        )
    }

    results: list[HybridSearchResult] = []
    for child_id in ranked_ids:
        child_text, metadata = child_by_id[child_id]
        parent_id = metadata["parent_id"]
        parent = parent_by_id.get(parent_id)
        if parent is None:
            raise ValueError(f"Parent chunk not found for child {child_id}")
        parent_text, parent_metadata = parent
        results.append(
            HybridSearchResult(
                child_id=child_id,
                child_text=child_text,
                parent_id=parent_id,
                parent_text=parent_text,
                source=str(metadata.get("source", parent_metadata.get("source", ""))),
                page=int(metadata.get("page", parent_metadata.get("page", 0))),
                score=fused_scores[child_id],
                semantic_rank=semantic_ranks.get(child_id),
                keyword_rank=keyword_ranks.get(child_id),
            )
        )
    return results


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.casefold())

from .index import IndexingResult, store_parent_child_chunks
from medicaldoc_rag.chunking.pipeline import run_chunking_pipeline


def run_indexing_pipeline() -> IndexingResult:
    """Run loading and chunking, then embed and persist both chunk levels."""
    parents, children = run_chunking_pipeline()
    return store_parent_child_chunks(parents, children)

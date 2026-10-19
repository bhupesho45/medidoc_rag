from pathlib import Path

from .index import IndexingResult, store_parent_child_chunks
from medicaldoc_rag.chunking.pipeline import run_chunking_pipeline
from medicaldoc_rag.loading.pipeline import UPLOAD_DIRECTORY


def run_indexing_pipeline(
    pdf_dir: str | Path = UPLOAD_DIRECTORY,
) -> IndexingResult:
    """Index uploaded PDFs from loading and chunking through vector storage."""
    parents, children = run_chunking_pipeline(pdf_dir=pdf_dir)
    return store_parent_child_chunks(parents, children)

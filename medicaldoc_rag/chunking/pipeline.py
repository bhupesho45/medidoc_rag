from pathlib import Path

from langchain_core.documents import Document

from medicaldoc_rag.loading.pipeline import UPLOAD_DIRECTORY, run_loading_pipeline

from .chunk import create_parent_child_chunks


def run_chunking_pipeline(
    pdf_dir: str | Path = UPLOAD_DIRECTORY,
) -> tuple[list[Document], list[Document]]:
    """Run phase 1 loading and return its parent and child chunks."""
    documents = run_loading_pipeline(pdf_dir=pdf_dir)
    return create_parent_child_chunks(documents)

from pathlib import Path

from fastapi import FastAPI
from langchain_core.documents import Document
from pydantic import BaseModel

from medicaldoc_rag.config import UPLOAD_DIRECTORY

from .clean import clean_documents
from .load import load_pdf_directory
from .metadata import build_page_metadata


PROJECT_ROOT = Path(__file__).resolve().parents[1]

app = FastAPI(title="MedicalDoc RAG - Loading")


def run_loading_pipeline(
    pdf_dir: str | Path = UPLOAD_DIRECTORY,
    project_root: str | Path = PROJECT_ROOT,
) -> list[Document]:
    """Load uploaded PDFs, clean page text, and attach retrieval-ready metadata."""
    loaded_pages = load_pdf_directory(pdf_dir)
    documents_with_metadata: list[Document] = []
    for source_path, page_number, raw_document in loaded_pages:
        cleaned = clean_documents([raw_document])
        if not cleaned:
            continue
        document = cleaned[0]
        document.metadata.update(
            build_page_metadata(source_path, page_number, project_root)
        )
        documents_with_metadata.append(document)

    return documents_with_metadata


class LoadedPage(BaseModel):
    page_content: str
    source: str
    page: int
    document_id: str


class LoadResponse(BaseModel):
    page_count: int
    documents: list[LoadedPage]


@app.post("/load", response_model=LoadResponse)
def load_documents() -> LoadResponse:
    """Load uploaded PDFs and return cleaned pages with metadata."""
    documents = run_loading_pipeline()
    return LoadResponse(
        page_count=len(documents),
        documents=[
            LoadedPage(
                page_content=document.page_content,
                source=document.metadata["source"],
                page=document.metadata["page"],
                document_id=document.metadata["document_id"],
            )
            for document in documents
        ],
    )

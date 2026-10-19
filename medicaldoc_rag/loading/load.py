from pathlib import Path

import pymupdf as fitz
from langchain_core.documents import Document


def load_pdf_pages(pdf_path: str | Path) -> list[tuple[int, Document]]:
    """Extract one LangChain document per page from a PDF."""
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF file not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, received: {path}")

    documents: list[tuple[int, Document]] = []
    with fitz.open(path) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            document = Document(page_content=page.get_text("text"))
            documents.append((page_number, document))
    return documents


def load_pdf_directory(
    pdf_dir: str | Path,
) -> list[tuple[Path, int, Document]]:
    """Load every PDF page in a directory, in a repeatable order."""
    directory = Path(pdf_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"PDF directory not found: {directory}")

    documents: list[tuple[Path, int, Document]] = []
    pdf_paths = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )
    for pdf_path in pdf_paths:
        documents.extend(
            (pdf_path, page_number, document)
            for page_number, document in load_pdf_pages(pdf_path)
        )
    return documents

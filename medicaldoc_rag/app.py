import hashlib
import re
from pathlib import Path
from uuid import uuid4

import chromadb
import pymupdf
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from groq import GroqError
from pydantic import BaseModel, Field

from medicaldoc_rag.generation import (
    configured_groq_model,
    generate_grounded_answer,
    groq_is_configured,
)
from medicaldoc_rag.indexing import run_indexing_pipeline
from medicaldoc_rag.indexing.index import (
    CHILD_COLLECTION_NAME,
    CHROMA_DIRECTORY,
    PARENT_COLLECTION_NAME,
)
from medicaldoc_rag.loading.pipeline import UPLOAD_DIRECTORY
from medicaldoc_rag.retrieval import hybrid_search


STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"
MAX_UPLOAD_FILES = 10
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
UPLOAD_READ_SIZE = 64 * 1024


def _upload_fingerprint(uploaded_pdfs: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(uploaded_pdfs):
        metadata = path.stat()
        digest.update(path.name.encode("utf-8"))
        digest.update(str(metadata.st_size).encode("ascii"))
        digest.update(str(metadata.st_mtime_ns).encode("ascii"))
    return digest.hexdigest()


app = FastAPI(
    title="MedicalDoc RAG",
    description="Source-grounded hybrid search over local medical documents.",
)
app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")


class ChatRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)


class Citation(BaseModel):
    child_id: str
    source: str
    page: int
    excerpt: str
    parent_context: str
    score: float
    semantic_rank: int | None
    keyword_rank: int | None


class ChatResponse(BaseModel):
    answer: str
    answer_mode: str
    query: str
    result_count: int
    citations: list[Citation]


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(STATIC_DIRECTORY / "index.html")


@app.get("/api/status")
def status() -> dict[str, object]:
    client = chromadb.PersistentClient(path=str(CHROMA_DIRECTORY))
    collection_names = {item.name for item in client.list_collections()}
    indexed = {
        CHILD_COLLECTION_NAME,
        PARENT_COLLECTION_NAME,
    }.issubset(collection_names)
    uploaded_pdfs = list(UPLOAD_DIRECTORY.glob("*.pdf"))
    if not uploaded_pdfs:
        return {
            "ready": False,
            "parent_count": 0,
            "child_count": 0,
            "document_count": 0,
            "llm_ready": groq_is_configured(),
            "llm_model": configured_groq_model(),
            "message": "Upload one or more PDFs to create your document index.",
        }
    try:
        fingerprint_path = UPLOAD_DIRECTORY / ".index-fingerprint"
        indexed_fingerprint = fingerprint_path.read_text(encoding="ascii")
        index_matches_uploads = indexed_fingerprint == _upload_fingerprint(uploaded_pdfs)
    except FileNotFoundError:
        index_matches_uploads = False
    indexed = indexed and index_matches_uploads
    if not indexed:
        return {
            "ready": False,
            "parent_count": 0,
            "child_count": 0,
            "document_count": len(uploaded_pdfs),
            "llm_ready": groq_is_configured(),
            "llm_model": configured_groq_model(),
            "message": "Index your uploaded PDFs to enable search.",
        }

    return {
        "ready": True,
        "parent_count": client.get_collection(PARENT_COLLECTION_NAME).count(),
        "child_count": client.get_collection(CHILD_COLLECTION_NAME).count(),
        "document_count": len(uploaded_pdfs),
        "llm_ready": groq_is_configured(),
        "llm_model": configured_groq_model(),
        "message": (
            "Hybrid search and Groq answer generation are ready."
            if groq_is_configured()
            else "Hybrid search is ready; configure GROQ_API_KEY to generate answers."
        ),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    query = request.query.strip()
    if len(query) < 2:
        raise HTTPException(status_code=422, detail="Enter a query with at least 2 characters.")

    state = status()
    if not state["ready"]:
        raise HTTPException(
            status_code=503,
            detail="Upload one or more PDFs and build the index before searching.",
        )

    results = hybrid_search(query, top_k=request.top_k)
    citations = [
        Citation(
            child_id=result.child_id,
            source=result.source,
            page=result.page,
            excerpt=result.child_text,
            parent_context=result.parent_text,
            score=result.score,
            semantic_rank=result.semantic_rank,
            keyword_rank=result.keyword_rank,
        )
        for result in results
    ]
    if citations:
        if groq_is_configured():
            try:
                answer = generate_grounded_answer(
                    query,
                    [
                        (citation.source, citation.page, citation.parent_context)
                        for citation in citations
                    ],
                )
            except ValueError as error:
                raise HTTPException(status_code=503, detail=str(error)) from error
            except GroqError as error:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Groq answer generation failed. Check the configured "
                        "API key, model, and network connection, then try again."
                    ),
                ) from error
            answer_mode = "groq"
        else:
            answer = (
                "Groq answer generation is not configured. The retrieved source "
                "passages are shown below; set GROQ_API_KEY locally to enable "
                "source-grounded answers."
            )
            answer_mode = "retrieval_only"
    else:
        answer = "No matching passages were found in the indexed documents. Try different terms or reindex the PDFs."
        answer_mode = "retrieval_only"
    return ChatResponse(
        answer=answer,
        answer_mode=answer_mode,
        query=query,
        result_count=len(citations),
        citations=citations,
    )


@app.post("/api/reindex")
def reindex() -> dict[str, object]:
    uploaded_pdfs = list(UPLOAD_DIRECTORY.glob("*.pdf"))
    if not uploaded_pdfs:
        raise HTTPException(
            status_code=409,
            detail="Upload at least one PDF before building the document index.",
        )
    fingerprint_path = UPLOAD_DIRECTORY / ".index-fingerprint"
    fingerprint_path.unlink(missing_ok=True)
    try:
        result = run_indexing_pipeline()
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    fingerprint_path.write_text(
        _upload_fingerprint(uploaded_pdfs),
        encoding="ascii",
    )
    return {
        "ready": True,
        "parent_count": result.parent_count,
        "child_count": result.child_count,
        "document_count": len(uploaded_pdfs),
        "message": "Uploaded PDFs loaded, chunked, embedded, and indexed.",
    }


@app.post("/api/upload")
def upload_documents(files: list[UploadFile] = File(...)) -> dict[str, object]:
    if not files:
        raise HTTPException(status_code=422, detail="Select at least one PDF to upload.")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"Upload no more than {MAX_UPLOAD_FILES} PDF files at a time.",
        )

    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    staged_paths: list[Path] = []
    stored_paths: list[Path] = []
    pending_files: list[tuple[Path, Path]] = []
    try:
        for upload in files:
            original_name = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
            if not original_name.lower().endswith(".pdf"):
                raise HTTPException(
                    status_code=415,
                    detail=f"{original_name or 'Each uploaded file'} must be a PDF.",
                )

            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", original_name).strip("._")
            if not safe_name:
                safe_name = "document.pdf"
            elif safe_name.lower().endswith(".pdf"):
                safe_name = f"{safe_name[:-4]}.pdf"
            else:
                safe_name += ".pdf"

            file_id = uuid4().hex
            staged_path = UPLOAD_DIRECTORY / f".upload-{file_id}.tmp"
            final_path = UPLOAD_DIRECTORY / f"{file_id}-{safe_name}"
            staged_paths.append(staged_path)
            pending_files.append((staged_path, final_path))
            size = 0
            signature = b""
            with staged_path.open("wb") as destination:
                while chunk := upload.file.read(UPLOAD_READ_SIZE):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"{original_name} exceeds the 20 MB per-file limit.",
                        )
                    if len(signature) < 5:
                        signature += chunk[: 5 - len(signature)]
                    destination.write(chunk)

            if not signature.startswith(b"%PDF-"):
                raise HTTPException(
                    status_code=415,
                    detail=f"{original_name} is not a valid PDF file.",
                )
            try:
                with pymupdf.open(
                    stream=staged_path.read_bytes(),
                    filetype="pdf",
                ) as pdf:
                    if not pdf.page_count:
                        raise HTTPException(
                            status_code=415,
                            detail=f"{original_name} does not contain any PDF pages.",
                        )
                    if not any(page.get_text("text").strip() for page in pdf):
                        raise HTTPException(
                            status_code=422,
                            detail=(
                                f"{original_name} has no extractable text. "
                                "Scanned PDFs require OCR, which is not supported."
                            ),
                        )
            except pymupdf.FileDataError as error:
                raise HTTPException(
                    status_code=415,
                    detail=f"{original_name} is not a readable PDF file.",
                ) from error
        for staged_path, final_path in pending_files:
            staged_path.replace(final_path)
            staged_paths.remove(staged_path)
            stored_paths.append(final_path)
        result = reindex()
    except HTTPException as error:
        if stored_paths:
            raise HTTPException(
                status_code=error.status_code,
                detail=f"PDFs were saved but could not be indexed: {error.detail}",
            ) from error
        raise
    except ValueError as error:
        detail = str(error)
        if stored_paths:
            detail = f"PDFs were saved but could not be indexed: {detail}"
        raise HTTPException(status_code=422, detail=detail) from error
    finally:
        for path in staged_paths:
            path.unlink(missing_ok=True)
        for upload in files:
            upload.file.close()

    return {
        "ready": result["ready"],
        "document_count": result["document_count"],
        "parent_count": result["parent_count"],
        "child_count": result["child_count"],
        "filenames": [path.name for path in stored_paths],
        "message": "Uploaded PDFs are indexed and ready for questions.",
    }
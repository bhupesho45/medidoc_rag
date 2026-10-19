from pathlib import Path
import chromadb
from fastapi import FastAPI, HTTPException
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
from medicaldoc_rag.retrieval import hybrid_search


STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"

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
    if not indexed:
        return {
            "ready": False,
            "parent_count": 0,
            "child_count": 0,
            "llm_ready": groq_is_configured(),
            "llm_model": configured_groq_model(),
            "message": "Index the bundled PDFs to enable search.",
        }

    return {
        "ready": True,
        "parent_count": client.get_collection(PARENT_COLLECTION_NAME).count(),
        "child_count": client.get_collection(CHILD_COLLECTION_NAME).count(),
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
            detail="The document index is not ready. Use Reindex documents first.",
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
    result = run_indexing_pipeline()
    return {
        "ready": True,
        "parent_count": result.parent_count,
        "child_count": result.child_count,
        "message": "Documents loaded, chunked, embedded, and indexed.",
    }
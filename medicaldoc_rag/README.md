# MedicalDoc RAG

MedicalDoc is a local, source-grounded search application for user-uploaded PDF
documents. It extracts and cleans PDF text, splits pages into linked parent and
child chunks, embeds and stores those chunks in ChromaDB, and combines semantic
search with BM25 keyword search. Upload PDFs in the browser, ask questions,
and inspect matching excerpts with their source page and wider parent context.

> **Medical information notice:** Generated responses are grounded in retrieved
> passages, but can be incomplete or incorrect. They are not medical advice,
> diagnosis, or treatment. Always consult a qualified healthcare professional.

## Features

- Extract text one page at a time from PDFs with PyMuPDF.
- Upload PDFs through the browser; uploaded files are stored locally and
  automatically indexed.
- Clean extracted text and attach stable source, page, and document metadata.
- Create overlapping parent and child chunks:
  - Parents: up to 1,000 characters, with 100 characters of overlap.
  - Children: up to 200 characters, with 40 characters of overlap.
- Generate local embeddings through ChromaDB's default embedding function.
- Persist parent and child documents in separate ChromaDB collections.
- Combine semantic and BM25 keyword rankings with reciprocal-rank fusion.
- Generate clearly structured, source-grounded answers with Groq when an API key is configured.
- Format generated answers into answer, evidence, and (when needed) limitations sections, with citations for factual claims.
- Return child excerpts, source citations, ranking details, and parent context.
- Serve a responsive browser interface and JSON API with FastAPI.

## Project layout

```text
medicaldoc_rag/
├── app.py                  # FastAPI application and JSON endpoints
├── data/pdfs/              # Bundled sample PDFs (not indexed)
├── data/uploads/           # User-uploaded PDFs (created locally; git-ignored)
├── loading/                # PDF extraction, cleaning, and metadata
├── chunking/               # Parent/child chunk generation
├── indexing/               # Embedding and persistent ChromaDB storage
├── retrieval/              # Hybrid semantic + BM25 search
├── generation/             # Grounded Groq answer generation
├── static/                 # Browser UI (HTML, CSS, JavaScript)
└── chroma_db/              # Persistent local vector database (created as needed)
```

## Requirements and setup

- Python 3.10 or newer.
- Internet access the first time ChromaDB downloads its default embedding model.

From the repository root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r medicaldoc_rag\loading\requirements.txt
```

If PowerShell blocks virtual-environment activation, allow it for the current
terminal session or invoke the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r medicaldoc_rag\loading\requirements.txt
```

The supplied sample PDFs in `medicaldoc_rag/data/pdfs/` are for reference only
and are not indexed. Add your own PDFs with **Upload PDFs** in the browser
interface. Uploaded files are stored locally in the ignored
`medicaldoc_rag/data/uploads/` directory and are the only files included in
the search index.

To keep uploads and the ChromaDB index on a Render persistent disk, set
`MEDICALDOC_DATA_DIR` to the disk's mount path (for example, `/var/data`).
The application stores uploads and ChromaDB beneath that directory. Without
the variable, it uses the project directory.

## Start the application

From the repository root with the virtual environment active:

```powershell
python -m uvicorn medicaldoc_rag.app:app --host 127.0.0.1 --port 8000 --reload
```

Open <http://127.0.0.1:8000> in a browser. The server binds to localhost and is
intended for local development.

### Configure Groq answer generation

Revoke the API key previously shared during setup and create a replacement. Do
not paste API keys into source files, README files, or chat. Add the replacement
key to the root `.env` file:

```dotenv
GROQ_API_KEY=your-replacement-key
GROQ_MODEL=openai/gpt-oss-120b
```

`.env` is ignored by Git and is loaded automatically when the application starts.
Keep the key private, and restart the server after changing it. Alternatively,
you can set `GROQ_API_KEY` in the server process environment. Without a key,
hybrid search remains available and the UI indicates that generated answers
are not configured.

Start the server from the repository root:

```powershell
python -m uvicorn medicaldoc_rag.app:app --host 127.0.0.1 --port 8000 --reload
```

`GROQ_MODEL` is optional; the default is `openai/gpt-oss-120b`.

**External data transfer:** When Groq is enabled, the user's question and the
retrieved passages used as answer context are sent to Groq's API. PDFs,
embeddings, and the ChromaDB index remain local. Do not use sensitive documents
unless you are authorized to send relevant excerpts to the configured provider.

The application does not automatically rebuild the index on startup. Use
**Upload PDFs** in the UI to add files and automatically index them. Uploaded
files persist locally in `medicaldoc_rag/data/uploads/`; subsequent uploads
are added to that local library. Use **Reindex documents** to rebuild the
index from all uploaded PDFs or call the reindex endpoint:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/reindex -Method Post
```

Reindexing reads only uploaded PDFs (not the bundled sample files), regenerates
chunks and embeddings, and replaces the existing index so removed/replaced
source content does not remain searchable. On a local machine, ChromaDB data
persists in `medicaldoc_rag/chroma_db/` across application restarts. Set
`MEDICALDOC_DATA_DIR` to use another data location. ChromaDB's default embedding
model may need to be downloaded the first time documents are indexed.

### Render filesystem persistence

Render Free web services use an ephemeral filesystem. Uploaded PDFs and
ChromaDB files may be lost when a free service restarts, spins down, or
redeploys; the service can then require PDFs to be uploaded and indexed again.
Free services cannot use a persistent disk. For durable storage, attach a
persistent disk to a paid web service and set `MEDICALDOC_DATA_DIR` to its mount
path (commonly `/var/data`). Only files under that mount path persist. See
[Render persistent disks](https://render.com/docs/disks) and
[Render Free services](https://render.com/docs/free).

## How the pipeline works

1. **Load:** `loading/load.py` extracts text from each uploaded PDF page.
2. **Clean and identify:** `loading/clean.py` normalizes whitespace and drops
   empty pages. `loading/metadata.py` adds stable source, page, and document IDs.
3. **Chunk:** `chunking/chunk.py` creates parent chunks and smaller child chunks.
   Each child includes the ID of its parent.
4. **Embed and store:** `indexing/index.py` embeds and persists parent and child
   records in the `medicaldoc_parents` and `medicaldoc_children` collections.
5. **Retrieve:** `retrieval/hybrid.py` ranks child chunks with ChromaDB semantic
   search and BM25 keyword search, fuses both rankings with reciprocal-rank
   fusion, and returns the corresponding parent context.
6. **Generate:** `generation/groq.py` sends retrieved passages and the query to
   Groq with instructions to stay within the evidence, cite claims, and say when
   the sources do not provide an answer.
7. **Present:** `app.py` exposes search and status endpoints; `static/` renders
   the answer, source citations, and expandable parent context.

## Use the browser interface

1. Start the server and open <http://127.0.0.1:8000>.
2. Select **Upload PDFs**, choose one or more text-based PDFs, and wait for
   indexing to complete. New uploads are indexed automatically. If you already
   have uploaded files but the header says **Index needed**, select
   **Reindex documents**.
3. Enter a question or choose one of the sample prompts.
4. Review the answer, ranked excerpts, source PDF and page, and
   semantic/keyword ranks.
5. Expand **View surrounding parent context** to see the larger chunk containing
   a matched child passage.
6. Check the status in the header to see whether Groq generation is configured.

Search examples:

- `What are common symptoms of type 2 diabetes?`
- `What does insulin do in the body?`
- `Which lifestyle factors can increase diabetes risk?`

## HTTP API

Interactive OpenAPI documentation is available at
<http://127.0.0.1:8000/docs>.

### `GET /api/status`

Returns whether both ChromaDB collections match the current uploaded PDFs and
the number of indexed documents, parent chunks, and child chunks.

### `POST /api/chat`

Request:

```json
{
  "query": "What are common symptoms of type 2 diabetes?",
  "top_k": 5
}
```

`query` must contain 2–2,000 characters. `top_k` is optional and accepts values
from 1 to 10 (default: 5). With Groq configured, `answer` contains a
source-grounded generated response and `answer_mode` is `groq`. Without a key,
`answer_mode` is `retrieval_only` and `answer` explains that generation is not
configured. The `citations` array contains child excerpts, parent context,
source paths, pages, reciprocal-rank-fusion scores, and semantic and keyword
ranks.

Example PowerShell request:

```powershell
$body = @{
    query = "What are common symptoms of type 2 diabetes?"
    top_k = 3
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri http://127.0.0.1:8000/api/chat `
    -Method Post `
    -ContentType "application/json" `
    -Body $body
```

### `POST /api/reindex`

Rebuilds the index from all user-uploaded PDFs in
`medicaldoc_rag/data/uploads/`. The operation returns the number of PDFs,
parent chunks, and child chunks indexed. It returns HTTP 409 if no PDFs have
been uploaded.

### `POST /api/upload`

Accepts multipart form data with one or more `files` fields. The UI uses this
endpoint when **Upload PDFs** is selected. Only PDF files are accepted, with
up to 10 files per request and a 20 MB limit per file. A successful upload
automatically rebuilds the index from all uploaded PDFs. Files and the index
remain on the local machine across application restarts; uploaded PDFs are
excluded from Git.

## Current scope and limitations

- Generated responses may be incomplete or incorrect even when grounded in
  citations; check the cited passages.
- The application does not diagnose, prescribe, or replace professional medical
  advice.
- BM25 is calculated from the indexed child texts during each search request;
  semantic vectors are persisted in ChromaDB.
- Only PDFs uploaded through the application are indexed; the bundled sample
  PDFs in `data/pdfs/` are not part of search.
- Uploads accumulate in the local library. There is not yet a UI/API for
  listing or deleting individual uploaded files.
- The first embedding-model download requires internet access. Groq generation
  requires internet access and a valid API key; PDF processing, embeddings, and
  retrieval otherwise run locally.
- When configured, the user's question and retrieved context are sent to Groq
  for answer generation.
- The development server is configured for localhost and has no authentication.
  Do not expose it to an untrusted network as-is.

## System design and technical choices

This is a document question-answering application built around retrieval-
augmented generation (RAG). It is not a trained medical model: it finds
passages in the PDFs you index and, when configured, asks a general-purpose
Groq-hosted language model to answer using those passages.

### End-to-end request flow

```text
PDF files
  -> PyMuPDF page extraction
  -> whitespace/control-character cleanup and page metadata
  -> overlapping parent chunks and smaller child chunks
  -> ChromaDB embeddings and persistent parent/child collections
  -> semantic retrieval + BM25 keyword retrieval
  -> reciprocal-rank fusion and parent-context lookup
  -> optional Groq answer generation
  -> API response and browser citations
```

1. **Load (`loading/`)** — `load.py` extracts text page by page from uploaded
   PDFs with PyMuPDF.
   `clean.py` removes control characters, normalizes whitespace, and skips
   blank pages. `metadata.py` records a source path relative to the project,
   one-based page number, and stable document ID. The loader reads `*.pdf`
   files from `data/uploads/`; PDFs without extractable text are rejected
   because scanned/image-only PDFs are not OCR'd.
2. **Chunk (`chunking/`)** — `chunk.py` uses LangChain's recursive character
   splitter to form 1,000-character parent chunks (100-character overlap) and
   200-character child chunks (40-character overlap). Child chunks carry a
   stable ID and their parent ID. Small child passages make retrieval more
   specific; the linked parent gives the answer generator more context.
3. **Index (`indexing/`)** — `index.py` writes parent and child text and
   metadata to separate persistent ChromaDB collections. ChromaDB's default
   embedding function creates vectors when adding documents and embeds a
   search query at query time. Stable IDs make repeated indexing of unchanged
   source documents consistent; each rebuild replaces the previous collections
   so stale content cannot remain searchable.
4. **Retrieve (`retrieval/`)** — `hybrid.py` runs vector similarity search on
   child chunks and BM25 keyword ranking over the indexed child text. It
   combines the two ranked lists with reciprocal-rank fusion (RRF), rather
   than trying to compare raw vector distances with BM25 scores. It then
   returns the best child passages together with their parent context, source,
   page, fused score, and ranks. The default result count is five; the API
   allows one to ten.
5. **Generate (`generation/`)** — when `GROQ_API_KEY` is set, `groq.py` sends
   the question and retrieved parent passages to the configured Groq model
   (default `openai/gpt-oss-120b`). The prompt instructs the model to stay
   within the retrieved evidence, cite supplied source markers, distinguish
   patient-specific details from general information, and avoid diagnosis or
   treatment advice. Otherwise, the API returns retrieval-only mode instead of
   failing the search.
6. **Present (`app.py`, `static/`)** — FastAPI serves the web page and JSON
   endpoints. The browser UI displays the answer, excerpts, source/page,
   semantic and keyword ranks, and expandable parent context. The status
   endpoint reports index counts and whether Groq is configured.

### Why these techniques were selected

| Choice | Purpose in this project | Trade-off |
|---|---|---|
| Page-level PDF extraction | Keeps page numbers available for citations and makes source passages traceable. | Text extraction quality depends on the PDF; image-only files need OCR, which is not implemented. |
| Recursive, overlapping parent/child chunks | Retrieves a compact passage while retaining surrounding context for generation; overlap reduces losses at split boundaries. | Character-based sizing is simple, but does not guarantee sentence or token boundaries. |
| ChromaDB persistent collections | Stores vectors, source text, and metadata locally between runs without a separate hosted vector database. | The default embedding model may need an initial download; local storage is not encrypted by this application. |
| Semantic plus BM25 retrieval | Semantic search can find related wording; BM25 helps exact terms and names. The combination covers complementary query styles. | BM25 corpus tokenization and ranking are rebuilt from stored child documents on every request, which is inefficient for a large corpus. |
| Reciprocal-rank fusion | Merges rankings without assuming semantic distances and BM25 scores share a scale. | RRF is a ranking heuristic; no evaluation dataset or tuned relevance threshold is included. |
| Optional Groq generation | Adds natural-language synthesis and citations while keeping retrieval usable without an API key. | With generation enabled, the question and retrieved context leave the machine; model-generated citations and claims still require checking against the sources. |
| FastAPI and a static browser UI | Provides a small local HTTP API and a browser workflow without a separate frontend build system. | There is no user authentication, multi-user isolation, or production deployment hardening. |

### API behavior and failure handling

- `GET /api/status` reports `ready`, parent/child counts, Groq readiness, and
  the configured model. An index is ready only when both expected collections
  exist and match the current set of uploaded PDFs.
- `POST /api/chat` validates the query (2–2,000 characters) and `top_k` (1–10).
  It returns the generated or retrieval-only answer plus citations. It returns
  HTTP 422 for invalid input, 503 if the index is unavailable or Groq
  configuration is invalid, and 502 if the Groq request fails.
- `POST /api/reindex` reruns PDF loading, chunking, and indexing from uploaded
  PDFs. Its response includes the PDF, parent, and child counts.
- `POST /api/upload` accepts multipart PDF uploads (up to 10 files, 20 MB
  each), stores them locally, and automatically rebuilds the index.
- FastAPI's interactive API documentation is at `/docs` while the server is
  running.

### What is implemented, and what is not

Implemented in this repository:

- Browser PDF upload, local storage, and page-numbered source metadata.
- Text cleanup, parent/child chunking, persistent vector indexing.
- Combined semantic and lexical retrieval with fused rankings.
- Optional evidence-oriented answer generation and source context in the API.
- A browser chat/search screen, service status, and a manual reindex action.

Not implemented (or not evidenced by this codebase):

- OCR, web search, other document formats, a UI/API for listing and deleting
  uploaded files, or per-user libraries.
- Login, role-based access, multi-user/session management, conversation
  history, or deployment security controls.
- Medical model fine-tuning, validated clinical decision support, or a
  guarantee that generated citations match every individual claim.
- Automated retrieval/answer quality evaluation or a checked-in test suite.

The PDFs uploaded to the local library are the knowledge base; adding PDFs
through the browser and reindexing changes what the system can retrieve. The
application itself does not validate medical correctness. It is an educational
document-search tool, not a clinician or a replacement for professional care.

## Similarity to the original MediRAG

**A defensible percentage match cannot be calculated from the files available
here.** This workspace contains the current MedicalDoc RAG implementation but
does not include a reference MediRAG repository, a specific release/commit, or
a requirements checklist for the original. "Percentage match" could mean
feature parity, workflow parity, UI similarity, or source-code similarity, and
those produce different results. Reporting a number without choosing and
checking that baseline would be misleading.

Based only on this repository, the project implements the standard core RAG
workflow—PDF text ingestion, chunking, embeddings, persistent vector storage,
hybrid retrieval, optional LLM synthesis, and citations. That describes the
features present here; it is **not** an estimate of percentage parity with
MediRAG. To calculate a meaningful feature-match percentage, compare this
feature list with the original project's URL/version or its specification and
agree which features count and how they are weighted.

## Operational and privacy notes

- By default, PDFs, extracted content, embeddings, and the ChromaDB index are
  stored locally. ChromaDB's default embedding model may be downloaded from
  the internet the first time indexing is run.
- If Groq generation is enabled, the question and retrieved passages are sent
  to the configured Groq API. Keep API credentials in the ignored local
  `.env` file or process environment; never commit them. Do not send sensitive
  documents unless authorized.
- The local development server has no authentication. Keep it bound to
  localhost and do not expose it to an untrusted network as-is.
- Always review the cited PDF passages. A citation makes an answer easier to
  verify; it does not establish that the answer is complete, correct, or safe
  medical advice.

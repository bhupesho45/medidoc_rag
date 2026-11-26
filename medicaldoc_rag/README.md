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

### Cloud upload and chat failures: what happened and what changed

Local success does not prove the deployed service has the same environment or
data. The local app and Render run as separate processes with separate
environment variables, installed runtime state, network access, and filesystems.
The following is the evidence-based history of the reported failures:

1. **Swagger showed `files` as strings and upload failed validation.** The
   upload route accepts `UploadFile` values in multipart form data, but the
   generated OpenAPI schema described the file items as strings. Swagger
   therefore did not reliably present/select actual binary PDFs; a request
   containing a string was rejected with HTTP 422 (`Expected UploadFile,
   received: str`). The OpenAPI schema now marks each `files` item as a binary
   `application/pdf`, and the browser sends the selected PDFs as `FormData`
   using the field name `files`.
2. **The browser reported `Unexpected token '<'`.** The UI attempted to parse
   every response as JSON. When a proxy or server returned an HTML error page,
   parsing began at its `<` character and failed, hiding the useful failure
   status/body. The frontend now handles JSON errors and non-JSON responses
   separately, displaying an actionable message instead of a JSON parse error.
3. **A deployed upload/index request later returned HTTP 502.** The service
   subsequently exposed the expected binary upload schema, accepted invalid
   PDFs with a clear JSON 415 response, and the user confirmed that valid PDFs
   indexed and appeared in status. The original 502's exact server-side cause
   was not established: its matching Render request logs/response body were
   unavailable. Do not treat the ephemeral filesystem as a confirmed cause;
   status showed an indexed document at the time of later checks.
4. **Chat also returned a generic HTTP 502 after indexing.** Upload/indexing
   and chat generation are separate requests. Chat first retrieves from
   ChromaDB, then calls Groq when `GROQ_API_KEY` is non-empty. Before the
   diagnostics changes, the UI showed only the status and Groq failures were
   not classified for the user. A non-empty key check does not validate that
   Render's secret is current/valid, that the selected model is available, or
   that the account has quota or network connectivity. Local synthetic Groq
   generation succeeded, but that does not test Render's environment.
5. **The historic chat 502's exact cause is also unconfirmed.** No Render log
   for that failing chat request was supplied, so it cannot be stated whether
   it was an invalid/unauthorized key, model/configuration rejection, quota or
   rate limit, network/provider failure, or another exception. The code now
   logs the Groq model, HTTP status when available, and exception type without
   logging the key, user query, or retrieved document passages. It returns
   more specific JSON errors for common Groq failures, and the UI shows those
   messages. Retrieval exceptions are logged and return HTTP 503 with
   reindex guidance.
6. **Weak or unrelated semantic matches could still reach generation.** The
   earlier retriever always included its nearest vector results, even when
   their distances were large. The hybrid retriever now filters semantic-only
   results beyond a 1.5 Chroma distance heuristic, while retaining keyword
   matches. If nothing qualifies, the API returns a no-matching-passages
   response without calling Groq. The cutoff is provisional: it was checked
   against a small local example, not a representative relevance test set.
7. **A separate empty-response error path could mask Groq's failure.** The
   generator referenced `GroqError` without importing it. That could raise a
   `NameError` when Groq returned empty content; the missing import is fixed.

**How to diagnose a future cloud failure:** open the matching Render log entry
at the exact request time and check the endpoint, HTTP status, and the new
error category. For a chat 502, verify Render's `GROQ_API_KEY` secret and
`GROQ_MODEL` setting, then check the logged provider status (401/403 suggests
credentials/permissions, 404 a model name, 429 rate/quota, and a connection
error network/provider connectivity). Never paste the API key into logs,
issues, or chat. For an upload/index failure, check the `/api/upload` response
body and Render logs; confirm `/api/status` reports ready and non-zero document
and chunk counts. After a free-service restart or deploy, re-upload PDFs and
reindex if the filesystem was cleared. For durable cloud data, use a Render
persistent disk on a supported paid service and point `MEDICALDOC_DATA_DIR`
to its mount path.

### Why an uploaded PDF may not be searchable

Uploading a PDF and retrieving an answer from it are different steps. A file
can upload successfully while some or all of its text is unavailable to search.
The supported workflow extracts embedded PDF text; it does not currently
perform OCR or search pixels in scanned page images.

| What you see | Why it can happen in this project | What to check or do |
|---|---|---|
| Upload returns “no extractable text” | The PDF contains scanned/image-only pages, or no page has text PyMuPDF can extract. The upload check rejects a document with no extractable page text. | Try selecting and copying text in a PDF reader. If the page is only an image, OCR it with a trusted tool to produce a searchable PDF, then upload that version. OCR is not built into this app. |
| A PDF uploads, but certain pages or sections are missing | Extraction uses `page.get_text("text")`. The cleaning step drops pages whose extracted text is empty. In a mixed PDF, digital-text pages can be indexed while image-only scanned pages are skipped. Complex layouts, unusual fonts, or damaged text encoding can also extract with missing or jumbled reading order. | Check the source PDF by copying text from the missing page. Make a searchable/OCR-processed copy if it is image-based. Review the retrieved page citation and excerpt to see what text was actually indexed. |
| The status shows PDFs, but zero chunks or search says the index is unavailable | The PDF files may exist without a matching completed ChromaDB index, indexing may have failed, or the current server filesystem may not contain the same uploads/index as before. `ready` requires uploaded PDFs and both ChromaDB collections to match the current upload fingerprint. | Check `/api/status` for `ready`, `document_count`, `parent_count`, and `child_count`; inspect the upload/reindex response and Render logs. Re-upload after a Render Free restart if the ephemeral filesystem was cleared, then reindex. |
| Search returns no passages even though the PDF has text | Retrieval is based on indexed child chunks, not a full-document keyword scan. BM25 needs token overlap with the query; semantic-only candidates farther than the configured 1.5 Chroma distance cutoff are discarded. A broad, differently worded, misspelled, or very specific question may therefore have no qualifying result. | Try distinctive terms that appear in the document, alternate wording, or a shorter question. Verify the expected passage appears in the indexed PDF text. Reindex after changing uploads. |
| Search finds passages, but the answer is incomplete | Only the highest-ranked child passages and their parent context are sent to Groq. The passage may omit the needed detail, the PDF may have extracted it poorly, or the model may not answer correctly despite the evidence. | Inspect the returned citations, page numbers, excerpts, and expanded parent context. Ask a narrower question using terms from the passage; do not rely on an answer that the cited text does not support. |

For cloud deployments, a successful local search proves only that the local
PDF text and local ChromaDB index work. Render has its own uploads, index,
environment, and filesystem. Render Free storage can be cleared on restarts or
redeploys, so the cloud may need the PDFs uploaded and indexed again. The
reported historical “some PDFs were not fetched” issue was not tied to a
specific PDF or a saved Render extraction log; these are the code-confirmed
reasons to check, not a claim that one particular cause was proven.

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
   fusion, and returns the corresponding parent context. Semantic-only matches
   must be within a conservative distance threshold; keyword matches can still
   be returned when that threshold is not met.
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
   excludes semantic-only matches beyond the configured Chroma distance
   cutoff, then combines semantic and keyword ranks with reciprocal-rank fusion
   (RRF), rather than comparing raw vector distances with BM25 scores. A
   keyword match can still be returned when it falls outside the semantic
   cutoff. The API returns the best child passages together with their parent
   context, source, page, fused score, and ranks. The default result count is
   five; the API allows one to ten.
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
| Reciprocal-rank fusion and semantic distance cutoff | Merges semantic and keyword rankings; filters weak semantic-only matches so unrelated questions do not automatically receive passages. | The 1.5 Chroma distance cutoff is a heuristic based on local checks, not an evaluated relevance threshold; tune it against a representative evaluation set before production use. |
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
  If retrieval produces no matching passages, the response explicitly says so
  and includes no citations rather than asking Groq to answer without evidence.
  Groq failures return readable JSON `detail` messages for authentication,
  model, quota/rate-limit, and connection errors; other provider failures
  include their HTTP status. Render logs include the configured model and
  provider status/error type, but not the API key, query, or retrieved passages.
  Retrieval exceptions are logged with a traceback and return a 503 asking for
  the index to be rebuilt.
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

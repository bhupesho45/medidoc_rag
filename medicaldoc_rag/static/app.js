const chatForm = document.querySelector("#chat-form");
const queryInput = document.querySelector("#query-input");
const sendButton = document.querySelector("#send-button");
const reindexButton = document.querySelector("#reindex-button");
const uploadButton = document.querySelector("#upload-button");
const pdfInput = document.querySelector("#pdf-input");
const messages = document.querySelector("#messages");
const welcome = document.querySelector("#welcome");
const errorBanner = document.querySelector("#error-banner");
const operationStatus = document.querySelector("#operation-status");
const statusText = document.querySelector("#status-text");
const statusIndicator = document.querySelector("#connection-status");
const documentCount = document.querySelector("#document-count");

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function showError(message) {
  operationStatus.hidden = true;
  errorBanner.textContent = message;
  errorBanner.hidden = false;
}

function clearError() {
  errorBanner.textContent = "";
  errorBanner.hidden = true;
}

function showOperationStatus(message) {
  operationStatus.textContent = message;
  operationStatus.hidden = false;
}

async function readApiResponse(response, fallbackMessage) {
  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : {};
  } catch {
    const detail = response.ok
      ? "The server returned an invalid response."
      : `The server returned a non-JSON error (HTTP ${response.status}). Check the deployment logs.`;
    throw new Error(`${fallbackMessage} ${detail}`);
  }

  if (!response.ok) {
    const detail = typeof payload.detail === "string"
      ? payload.detail
      : Array.isArray(payload.detail)
        ? payload.detail
            .map((item) => item.msg)
            .filter(Boolean)
            .join("; ") || `Request failed (HTTP ${response.status}).`
        : typeof payload.message === "string"
          ? payload.message
          : `Request failed (HTTP ${response.status}).`;
    throw new Error(detail);
  }
  return payload;
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    const state = await readApiResponse(response, "Could not read index status.");
    statusText.textContent = !state.ready
      ? state.document_count
        ? "Index needed"
        : "Upload PDFs"
      : state.llm_ready
        ? "Index · Groq ready"
        : "Index ready · Groq key needed";
    statusIndicator.classList.toggle("offline", !state.ready);
    documentCount.textContent = state.ready
      ? `${state.document_count} PDFs · ${state.child_count} chunks`
      : state.document_count
        ? `${state.document_count} PDFs · Not indexed`
        : "Upload a PDF";
  } catch (error) {
    statusText.textContent = "Offline";
    statusIndicator.classList.add("offline");
    documentCount.textContent = "Unavailable";
    showError(error.message);
  }
}

function appendCitation(result, index) {
  const card = makeElement("article", "citation-card");
  const meta = makeElement("div", "citation-meta");
  meta.append(
    makeElement("span", "source-pill", result.source || "Source document"),
    makeElement("span", "page-pill", `Page ${result.page}`),
    makeElement(
      "span",
      "rank-label",
      `Semantic #${result.semantic_rank ?? "—"} · Keyword #${result.keyword_rank ?? "—"}`,
    ),
  );
  card.append(meta);
  card.append(makeElement("p", "citation-excerpt", result.excerpt));

  const details = document.createElement("details");
  details.append(makeElement("summary", "", "View surrounding parent context"));
  details.append(makeElement("p", "parent-context", result.parent_context));
  card.append(details);
  card.setAttribute("aria-label", `Source passage ${index + 1}`);
  return card;
}

function appendResponse(data) {
  const response = makeElement("section", "message-assistant");
  const heading = makeElement("div", "assistant-heading");
  const answerLabel =
    data.answer_mode === "groq" ? "Generated with Groq · source-grounded" : "Retrieved sources";
  heading.append(
    makeElement("span", "assistant-mark", "✳"),
    makeElement("span", "", "MedicalDoc"),
    makeElement("span", "answer-mode", answerLabel),
  );
  response.append(heading);
  response.append(makeElement("p", "answer-copy", data.answer));
  if (data.citations.length) {
    const list = makeElement("div", "citation-list");
    data.citations.forEach((citation, index) => {
      list.append(appendCitation(citation, index));
    });
    response.append(list);
  }
  messages.append(response);
  response.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function submitQuery(query) {
  const cleanedQuery = query.trim();
  if (cleanedQuery.length < 2) {
    showError("Enter at least two characters to search.");
    return;
  }

  clearError();
  welcome.hidden = true;
  const userMessage = makeElement("div", "message-user");
  userMessage.append(makeElement("p", "", cleanedQuery));
  messages.append(userMessage);
  const loading = makeElement("div", "loading-message");
  loading.append(
    makeElement("span", "spinner"),
    makeElement("span", "", "Retrieving sources and drafting a grounded answer…"),
  );
  messages.append(loading);
  sendButton.disabled = true;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: cleanedQuery, top_k: 5 }),
    });
    const payload = await readApiResponse(response, "Search failed.");
    appendResponse(payload);
  } catch (error) {
    showError(error.message || "Could not reach the search service.");
  } finally {
    loading.remove();
    sendButton.disabled = false;
    queryInput.focus();
  }
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = queryInput.value;
  queryInput.value = "";
  queryInput.style.height = "auto";
  submitQuery(query);
});

queryInput.addEventListener("input", () => {
  queryInput.style.height = "auto";
  queryInput.style.height = `${Math.min(queryInput.scrollHeight, 110)}px`;
});

queryInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

document.querySelectorAll(".suggestion").forEach((button) => {
  button.addEventListener("click", () => submitQuery(button.dataset.query));
});

reindexButton.addEventListener("click", async () => {
  clearError();
  reindexButton.disabled = true;
  uploadButton.disabled = true;
  reindexButton.textContent = "Indexing…";
  statusText.textContent = "Indexing";
  try {
    const response = await fetch("/api/reindex", { method: "POST" });
    await readApiResponse(response, "Reindexing failed.");
    await refreshStatus();
    showOperationStatus("Your uploaded PDFs have been reindexed.");
  } catch (error) {
    showError(error.message || "Could not reindex documents.");
    statusText.textContent = "Index error";
    statusIndicator.classList.add("offline");
  } finally {
    reindexButton.disabled = false;
    uploadButton.disabled = false;
    reindexButton.innerHTML = "<span aria-hidden=\"true\">↻</span> Reindex documents";
  }
});

uploadButton.addEventListener("click", () => pdfInput.click());

pdfInput.addEventListener("change", async () => {
  const selectedFiles = Array.from(pdfInput.files || []);
  if (!selectedFiles.length) return;

  const invalidFile = selectedFiles.find(
    (file) => !file.name.toLowerCase().endsWith(".pdf") || file.size > 20 * 1024 * 1024,
  );
  if (invalidFile) {
    showError(
      invalidFile.size > 20 * 1024 * 1024
        ? `${invalidFile.name} exceeds the 20 MB per-file limit.`
        : `${invalidFile.name} is not a PDF.`,
    );
    pdfInput.value = "";
    return;
  }
  if (selectedFiles.length > 10) {
    showError("Upload no more than 10 PDF files at a time.");
    pdfInput.value = "";
    return;
  }

  clearError();
  uploadButton.disabled = true;
  reindexButton.disabled = true;
  uploadButton.textContent = "Uploading…";
  statusText.textContent = "Uploading and indexing";
  showOperationStatus(`Uploading and indexing ${selectedFiles.length} PDF file(s)…`);
  const formData = new FormData();
  selectedFiles.forEach((file) => formData.append("files", file));

  try {
    const response = await fetch("/api/upload", { method: "POST", body: formData });
    const payload = await readApiResponse(response, "PDF upload failed.");
    await refreshStatus();
    showOperationStatus(
      `Uploaded and indexed ${payload.document_count} PDF file(s). You can now ask questions about them.`,
    );
  } catch (error) {
    showError(error.message || "Could not upload the selected PDFs.");
    statusText.textContent = "Upload error";
    statusIndicator.classList.add("offline");
  } finally {
    pdfInput.value = "";
    uploadButton.disabled = false;
    reindexButton.disabled = false;
    uploadButton.innerHTML = "<span aria-hidden=\"true\">＋</span> Upload PDFs";
  }
});

refreshStatus();

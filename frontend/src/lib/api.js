const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
    const detail = typeof payload === "object" && payload !== null ? payload.detail || payload : null;
    this.code = detail?.error_code || null;
    this.fallbackOptions = Array.isArray(detail?.fallback_options) ? detail.fallback_options : [];
  }
}

function friendlyErrorMessage(status, payload) {
  const detail = typeof payload === "object" && payload !== null ? payload.detail : null;
  const rawMessage =
    typeof payload === "string"
      ? payload
      : typeof detail === "string"
        ? detail
        : detail?.message || payload?.message || payload?.error || "";
  const message = String(rawMessage || "").trim();
  const lower = message.toLowerCase();
  const errorCode = typeof detail === "object" && detail !== null ? detail.error_code : null;

  if (!message) {
    if (status === 0) return "Backend unavailable. Start the SAGE backend and try again.";
    return "Request failed. Please try again.";
  }

  if (status === 401 || status === 403) {
    return "You do not have permission to access this resource.";
  }

  if (status === 404) {
    if (lower.includes("github") || lower.includes("repository")) return "GitHub repo not found or inaccessible.";
    if (lower.includes("job")) return "Job not found. It may have expired.";
    if (lower.includes("source")) return "Source not found.";
    return message;
  }

  if (status === 415 && lower.includes("pdf")) {
    return "PDF upload failed. Please provide a valid PDF file.";
  }

  if (status === 422) {
    if (errorCode === "WEBSITE_NO_USABLE_TEXT") return message;
    if (lower.includes("url")) return "Invalid URL. Please check the address and try again.";
    if (lower.includes("transcript")) return "YouTube transcript unavailable for this video.";
    if (lower.includes("repository")) return "GitHub repo not found or inaccessible.";
  }

  if (status === 504 && errorCode === "WEBSITE_CRAWL_TIMEOUT") {
    return message || "Website crawl timed out. Please try again with fewer pages.";
  }

  if (lower.includes("backend unavailable") || lower.includes("failed to fetch")) {
    return "Backend unavailable. Start the SAGE backend and try again.";
  }

  if (lower.includes("supabase")) {
    return "Supabase error while saving or loading data.";
  }

  if (lower.includes("groq")) {
    return "Groq error while generating the answer.";
  }

  if (lower.includes("timeout") || lower.includes("timed out")) {
    return "Request timed out. Please try again.";
  }

  return message || "Request failed. Please try again.";
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  let payload;

  try {
    payload = contentType.includes("application/json") ? await response.json() : await response.text();
  } catch {
    payload = "";
  }

  if (!response.ok) {
    throw new ApiError(friendlyErrorMessage(response.status, payload), response.status, payload);
  }

  return payload;
}

async function requestJson(url, options = {}) {
  try {
    const response = await fetch(url, options);
    return await parseResponse(response);
  } catch (error) {
    if (error instanceof TypeError || /failed to fetch/i.test(String(error?.message || ""))) {
      throw new Error("Backend unavailable. Start the SAGE backend and try again.");
    }
    throw error;
  }
}

export async function listSources() {
  return requestJson(`${API_BASE}/sources`);
}

export async function listSourcesGrouped() {
  return requestJson(`${API_BASE}/sources/grouped`);
}

export async function getSourceBrief(sourceId, refresh = false) {
  return requestJson(`${API_BASE}/sources/${sourceId}/brief${refresh ? "?refresh=true" : ""}`);
}

export async function getEvidence(chunkId, claims) {
  return requestJson(`${API_BASE}/qa/evidence`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chunk_id: chunkId, claims: claims.slice(0, 10) }),
  });
}

export async function getSourceDetails(sourceId) {
  return requestJson(`${API_BASE}/sources/${sourceId}`);
}

export async function getKnowledgebaseDetails(knowledgebaseId) {
  return requestJson(`${API_BASE}/sources/knowledgebases/${knowledgebaseId}`);
}

export async function deleteSource(sourceId) {
  return requestJson(`${API_BASE}/sources/${sourceId}`, {
    method: "DELETE"
  });
}

export async function deleteKnowledgebase(knowledgebaseId) {
  return requestJson(`${API_BASE}/sources/knowledgebases/${knowledgebaseId}`, {
    method: "DELETE"
  });
}

export async function recrawlWebsite(request) {
  return requestJson(`${API_BASE}/sources/website/recrawl`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request)
  });
}

export async function getJobStatus(jobId) {
  return requestJson(`${API_BASE}/jobs/${jobId}`);
}

export async function startWebsiteIngestJob(url, maxPages = 10, maxDepth = 1) {
  return requestJson(`${API_BASE}/jobs/website-ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, max_pages: maxPages, max_depth: maxDepth })
  });
}

export async function startPdfIngestJob(file) {
  const formData = new FormData();
  formData.append("file", file);
  return requestJson(`${API_BASE}/jobs/pdf-ingest`, {
    method: "POST",
    body: formData
  });
}

export async function startVideoIngestJob(url) {
  return requestJson(`${API_BASE}/ingest/video`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url })
  });
}

export async function startVideoAutoTranscribeJob(url) {
  return requestJson(`${API_BASE}/jobs/video-auto-transcribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url })
  });
}

export async function startGithubIngestJob(url, branch = null) {
  return requestJson(`${API_BASE}/jobs/github-ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, branch })
  });
}

export async function ingestWebsite(url, maxPages = 10, maxDepth = 1) {
  return requestJson(`${API_BASE}/ingest/website`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, max_pages: maxPages, max_depth: maxDepth })
  });
}

export async function ingestPdf(file) {
  const formData = new FormData();
  formData.append("file", file);
  return requestJson(`${API_BASE}/ingest/pdf`, {
    method: "POST",
    body: formData
  });
}

export async function askQuestion({ question, mode, knowledgebase_id, source_id, source_ids, history, top_k = 6 }) {
  return requestJson(`${API_BASE}/qa/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, mode, knowledgebase_id, source_id, source_ids, history, top_k })
  });
}

// Streams the answer token-by-token over SSE. Calls onMeta once (citations,
// confidence, etc.), onDelta for each text chunk, then onDone with the final
// assembled answer + warnings. Throws ApiError up front if the request itself
// fails to even start (bad request, backend down).
export async function askQuestionStream(
  { question, mode, knowledgebase_id, source_id, source_ids, history, top_k = 6 },
  { onMeta, onDelta, onDone, signal } = {}
) {
  let response;
  try {
    response = await fetch(`${API_BASE}/qa/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, mode, knowledgebase_id, source_id, source_ids, history, top_k }),
      signal
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new Error("Backend unavailable. Start the SAGE backend and try again.");
  }

  if (!response.ok || !response.body) {
    await parseResponse(response); // throws a friendly ApiError
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let eventName = "message";
      let data = "";
      for (const line of rawEvent.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      const parsed = JSON.parse(data);
      if (eventName === "meta") onMeta?.(parsed);
      else if (eventName === "delta") onDelta?.(parsed.text);
      else if (eventName === "done") onDone?.(parsed);
      else if (eventName === "error") throw new ApiError(parsed.message || "Question answering failed.");
    }
  }
}

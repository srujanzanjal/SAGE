const DEFAULT_BACKEND_URL = "http://localhost:8000/api/v1";
const STORAGE_KEYS = {
  backendUrl: "sageBackendUrl",
  activeJob: "sageActiveIngestJob",
};
const MAX_HISTORY_TURNS = 6;
const STALL_TIMEOUT_MS = 30000;

const state = {
  backendUrl: DEFAULT_BACKEND_URL,
  currentTab: null,
  sources: [],
  selectedSourceIds: [],
  messages: [], // { question, streaming, answer: { text, citations, confidence_score, confidence_label, confidence_reason, follow_up_question, warnings } }
};

let activeStreamController = null;

function $(id) {
  return document.getElementById(id);
}

function setStatus(message, kind = "info") {
  const el = $("backend-status");
  el.textContent = message;
  el.dataset.kind = kind;
}

function setQaStatus(message, kind = "info") {
  const el = $("qa-status");
  el.textContent = message;
  el.dataset.kind = kind;
}

function detectWebsiteSupport(tab) {
  const url = tab?.url || "";
  if (!/^https?:\/\//i.test(url)) return "unsupported";
  if (/youtube\.com|youtu\.be/i.test(url)) return "main_app_video";
  if (/github\.com/i.test(url)) return "main_app_github";
  if (/\.pdf(?:[?#]|$)/i.test(url)) return "main_app_pdf";
  return "website";
}

function unsupportedMessage(type) {
  return {
    main_app_video: "Video Intelligence is available in the main SAGE web app.",
    main_app_github: "GitHub Intelligence is available in the main SAGE web app.",
    main_app_pdf: "PDF upload is available in the main SAGE web app.",
    unsupported: "This page type is not supported by the website-only extension.",
  }[type] || "Unsupported page.";
}

function apiRoot() {
  return state.backendUrl.replace(/\/api\/v1\/?$/, "");
}

// Every plain request gets a bounded timeout so a hung backend shows a clear
// error instead of a spinner that never resolves.
async function requestJson(path, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(`${state.backendUrl}${path}`, { ...options, signal: controller.signal });
  } catch (error) {
    if (error.name === "AbortError") throw new Error("Request timed out. Is the backend running and responsive?");
    throw new Error("Could not reach the backend. Is it running?");
  } finally {
    clearTimeout(timer);
  }
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === "string" ? payload : payload?.detail || payload?.message || payload?.error;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail) || "Request failed");
  }
  return payload;
}

async function checkBackend() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6000);
  try {
    const response = await fetch(`${apiRoot()}/health`, { signal: controller.signal });
    if (!response.ok) throw new Error("Backend health check failed.");
    setStatus("Backend is running.", "success");
    return true;
  } catch (error) {
    const message = error.name === "AbortError"
      ? "Backend did not respond within 6s. Is it running?"
      : "SAGE backend is not running. Start it with: cd backend && python run.py";
    setStatus(message, "error");
    return false;
  } finally {
    clearTimeout(timer);
  }
}

async function loadBackendUrl() {
  const result = await chrome.storage.local.get([STORAGE_KEYS.backendUrl]);
  state.backendUrl = result[STORAGE_KEYS.backendUrl] || DEFAULT_BACKEND_URL;
  $("backend-url").value = state.backendUrl;
}

async function saveBackendUrl() {
  state.backendUrl = $("backend-url").value.trim() || DEFAULT_BACKEND_URL;
  await chrome.storage.local.set({ [STORAGE_KEYS.backendUrl]: state.backendUrl });
  setStatus(`Saved backend URL: ${state.backendUrl}`, "success");
}

async function refreshCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  state.currentTab = tab
    ? { url: tab.url || "", title: tab.title || "", sourceType: detectWebsiteSupport(tab) }
    : null;
  renderCurrentTab();
}

function renderCurrentTab() {
  const tab = state.currentTab;
  const type = tab?.sourceType || "unsupported";
  $("tab-type").textContent = type === "website" ? "Website" : "Main app / unsupported";
  $("tab-type").className = `badge ${type}`;
  $("tab-title").textContent = tab?.title || "No tab selected";
  $("tab-url").textContent = tab?.url || "";
  $("tab-summary").textContent = type === "website"
    ? "Website page detected. You can crawl it from this side panel."
    : unsupportedMessage(type);
}

function useCurrentTab() {
  const tab = state.currentTab;
  if (!tab) {
    setStatus("No active tab available.", "error");
    return;
  }
  if (tab.sourceType !== "website") {
    setStatus(unsupportedMessage(tab.sourceType), "error");
    return;
  }
  $("source-url").value = tab.url;
  setStatus("Loaded current website URL.", "success");
}

function toggleSource(sourceId) {
  state.selectedSourceIds = state.selectedSourceIds.includes(sourceId)
    ? state.selectedSourceIds.filter((id) => id !== sourceId)
    : [...state.selectedSourceIds, sourceId];
  renderSourceCards();
}

function updateSelectedSourcesSummary() {
  const el = $("selected-sources-summary");
  const selected = state.sources.filter((s) => state.selectedSourceIds.includes(s.source_id));
  if (!selected.length) {
    el.textContent = "No source selected.";
  } else if (selected.length === 1) {
    el.textContent = `Selected: ${selected[0].title || selected[0].original_ref}`;
  } else {
    el.textContent = `Combining ${selected.length} sources for this question.`;
  }
  $("ask-button").disabled = selected.length === 0;
}

function renderSourceCards() {
  const container = $("sources-list");
  container.innerHTML = "";
  if (!state.sources.length) {
    const empty = document.createElement("div");
    empty.className = "source-item";
    empty.innerHTML = '<div class="source-item-body"><div class="source-title">No website sources yet</div><div class="source-meta">Crawl a website first.</div></div>';
    container.append(empty);
    updateSelectedSourcesSummary();
    return;
  }
  for (const source of state.sources) {
    const selected = state.selectedSourceIds.includes(source.source_id);
    const card = document.createElement("label");
    card.className = `source-item ${selected ? "selected" : ""}`;

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selected;
    checkbox.addEventListener("change", () => toggleSource(source.source_id));

    const body = document.createElement("div");
    body.className = "source-item-body";
    const title = document.createElement("div");
    title.className = "source-title";
    title.textContent = source.title || source.original_ref || "Website source";
    const meta = document.createElement("div");
    meta.className = "source-meta";
    meta.textContent = [source.status, source.canonical_ref].filter(Boolean).join(" · ");
    const tags = document.createElement("div");
    tags.className = "source-tags";
    for (const label of ["website", `${source.chunks_count ?? 0} chunks`, source.crawled_pages ? `${source.crawled_pages} pages` : null].filter(Boolean)) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = label;
      tags.append(tag);
    }
    body.append(title, meta, tags);
    card.append(checkbox, body);
    container.append(card);
  }
  updateSelectedSourcesSummary();
}

async function loadSources() {
  try {
    setStatus("Loading website sources...", "info");
    const payload = await requestJson("/sources");
    state.sources = Array.isArray(payload) ? payload.filter((s) => s.source_type === "website" && s.status === "ready") : [];
    state.selectedSourceIds = state.selectedSourceIds.filter((id) => state.sources.some((s) => s.source_id === id));
    renderSourceCards();
    setStatus(`Loaded ${state.sources.length} website source${state.sources.length === 1 ? "" : "s"}.`, "success");
  } catch (error) {
    setStatus(error.message || "Failed to load sources.", "error");
  }
}

// --- Ingest job tracking (persisted so a re-opened panel can resume watching it) ---

async function storeActiveJob(jobId, sourceUrl) {
  await chrome.storage.local.set({ [STORAGE_KEYS.activeJob]: { jobId, sourceUrl, startedAt: new Date().toISOString() } });
}

async function clearActiveJob() {
  await chrome.storage.local.remove([STORAGE_KEYS.activeJob]);
}

async function getStoredActiveJob() {
  const result = await chrome.storage.local.get([STORAGE_KEYS.activeJob]);
  return result[STORAGE_KEYS.activeJob] || null;
}

function showIngestProgress(job) {
  $("ingest-progress").classList.remove("hidden");
  $("ingest-progress-fill").style.width = `${job.progress_percentage || 0}%`;
  $("ingest-progress-label").textContent = job.message || job.current_step || "Working...";
}

async function pollJob(jobId) {
  for (;;) {
    const job = await requestJson(`/jobs/${jobId}`, {}, 15000);
    showIngestProgress(job);
    if (job.status === "completed" || job.status === "failed") {
      await clearActiveJob();
      return job;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}

async function resumeActiveJobIfAny() {
  const stored = await getStoredActiveJob();
  if (!stored) return;
  try {
    const job = await requestJson(`/jobs/${stored.jobId}`, {}, 8000);
    if (job.status !== "processing") {
      await clearActiveJob();
      return;
    }
    setStatus(`Resuming crawl for ${stored.sourceUrl}...`, "info");
    $("ingest-button").disabled = true;
    const result = await pollJob(stored.jobId);
    await loadSources();
    setStatus(result.status === "failed" ? "Website crawl failed." : "Website crawl complete.", result.status === "failed" ? "error" : "success");
  } catch {
    // Job likely expired from the backend's in-memory tracker while the panel was closed.
    await clearActiveJob();
  } finally {
    $("ingest-button").disabled = false;
  }
}

async function ingestCurrentWebsite() {
  const sourceUrl = $("source-url").value.trim();
  const maxPages = Number($("max-pages").value || 10);
  const maxDepth = Number($("max-depth").value || 1);
  if (!sourceUrl) throw new Error("Enter a website URL first.");
  if (!/^https?:\/\//i.test(sourceUrl)) throw new Error("Only http/https website URLs are supported.");

  $("ingest-button").disabled = true;
  try {
    if (!(await checkBackend())) return;
    setStatus("Starting website crawl...", "info");
    showIngestProgress({ progress_percentage: 1, message: "Starting crawl" });
    let result = await requestJson(
      "/jobs/website-ingest",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: sourceUrl, max_pages: maxPages, max_depth: maxDepth }) },
      20000
    );
    await storeActiveJob(result.job_id, sourceUrl);
    result = await pollJob(result.job_id);
    await loadSources();
    const createdId = result.result?.sources_created?.[0]?.source_id;
    if (createdId && !state.selectedSourceIds.includes(createdId)) {
      state.selectedSourceIds = [createdId];
      renderSourceCards();
    }
    setStatus(result.status === "failed" ? "Website crawl failed." : "Website crawl complete.", result.status === "failed" ? "error" : "success");
  } finally {
    $("ingest-button").disabled = false;
  }
}

// --- Streaming Q&A with conversation memory ---

async function streamAnswer(payload, handlers, signal) {
  const response = await fetch(`${state.backendUrl}/qa/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok || !response.body) {
    const contentType = response.headers.get("content-type") || "";
    const errPayload = contentType.includes("application/json") ? await response.json() : await response.text();
    const detail = typeof errPayload === "string" ? errPayload : errPayload?.detail || errPayload?.message;
    throw new Error(typeof detail === "string" ? detail : "Question answering failed.");
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
      if (eventName === "meta") handlers.onMeta?.(parsed);
      else if (eventName === "delta") handlers.onDelta?.(parsed.text);
      else if (eventName === "done") handlers.onDone?.(parsed);
      else if (eventName === "error") throw new Error(parsed.message || "Question answering failed.");
    }
  }
}

function confidenceClass(label) {
  const l = (label || "").toLowerCase();
  if (l === "high") return "high";
  if (l === "medium") return "medium";
  if (l === "low") return "low";
  return "";
}

function renderChatThread() {
  const container = $("chat-thread");
  const newChatBtn = $("new-chat");
  if (!state.messages.length) {
    container.classList.add("hidden");
    newChatBtn.classList.add("hidden");
    container.innerHTML = "";
    return;
  }
  container.classList.remove("hidden");
  newChatBtn.classList.remove("hidden");
  container.innerHTML = "";

  state.messages.forEach((msg, idx) => {
    const qBubble = document.createElement("div");
    qBubble.className = "chat-turn-question";
    qBubble.textContent = msg.question;
    container.append(qBubble);

    const answerBox = document.createElement("div");
    answerBox.className = "chat-turn-answer";

    const header = document.createElement("div");
    header.className = "chat-turn-answer-header";
    const label = document.createElement("span");
    label.style.fontSize = "11px";
    label.style.fontWeight = "700";
    label.style.color = "#334155";
    label.style.textTransform = "uppercase";
    label.style.letterSpacing = "0.06em";
    label.textContent = "SAGE Answer";
    header.append(label);
    if (msg.answer.confidence_label) {
      const badge = document.createElement("span");
      badge.className = `confidence-badge ${confidenceClass(msg.answer.confidence_label)}`;
      const pct = typeof msg.answer.confidence_score === "number" ? ` ${Math.round(msg.answer.confidence_score * 100)}%` : "";
      badge.textContent = `${msg.answer.confidence_label}${pct}`;
      header.append(badge);
    }
    answerBox.append(header);

    const textEl = document.createElement("div");
    textEl.className = "chat-turn-answer-text";
    textEl.textContent = msg.answer.text;
    if (msg.streaming) {
      const cursor = document.createElement("span");
      cursor.className = "stream-cursor";
      textEl.append(cursor);
    }
    answerBox.append(textEl);

    for (const warning of msg.answer.warnings || []) {
      const w = document.createElement("div");
      w.className = "warning-line";
      w.textContent = warning;
      answerBox.append(w);
    }

    if (msg.answer.citations?.length) {
      const list = document.createElement("div");
      list.className = "citation-list";
      for (const citation of msg.answer.citations) {
        const chip = document.createElement("div");
        chip.className = "citation-chip";
        const strong = document.createElement("b");
        strong.textContent = `${citation.citation_id} `;
        chip.append(strong, document.createTextNode(citation.source_title || citation.source_ref || "Source"));
        list.append(chip);
      }
      answerBox.append(list);
    }

    if (!msg.streaming && msg.answer.follow_up_question && idx === state.messages.length - 1) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "followup-chip";
      chip.textContent = msg.answer.follow_up_question;
      chip.addEventListener("click", () => {
        askQuestion(msg.answer.follow_up_question).catch((error) => setQaStatus(error.message, "error"));
      });
      answerBox.append(chip);
    }

    container.append(answerBox);
  });

  container.scrollTop = container.scrollHeight;
}

function startNewChat() {
  activeStreamController?.abort();
  state.messages = [];
  renderChatThread();
  setQaStatus("", "info");
}

async function askQuestion(overrideQuestion) {
  const question = (overrideQuestion ?? $("question").value).trim();
  const mode = $("qa-mode").value;
  const topK = Number($("top-k").value || 6);
  if (!state.selectedSourceIds.length) throw new Error("Select at least one website source first.");
  if (!question) throw new Error("Enter a question first.");

  const history = state.messages.slice(-MAX_HISTORY_TURNS).map((m) => ({ question: m.question, answer: m.answer.text }));

  activeStreamController?.abort();
  const controller = new AbortController();
  activeStreamController = controller;
  let stallTimer = setTimeout(() => controller.abort(), STALL_TIMEOUT_MS);
  const bumpStallTimer = () => {
    clearTimeout(stallTimer);
    stallTimer = setTimeout(() => controller.abort(), STALL_TIMEOUT_MS);
  };

  $("ask-button").disabled = true;
  $("question").value = "";
  setQaStatus("Asking...", "info");

  const message = {
    question,
    streaming: true,
    answer: { text: "", citations: [], confidence_score: null, confidence_label: null, confidence_reason: null, follow_up_question: null, warnings: [] },
  };
  state.messages.push(message);
  renderChatThread();

  try {
    await streamAnswer(
      { question, mode, source_ids: state.selectedSourceIds, history, top_k: topK },
      {
        onMeta: (meta) => {
          bumpStallTimer();
          message.answer = { ...message.answer, ...meta };
          renderChatThread();
        },
        onDelta: (text) => {
          bumpStallTimer();
          message.answer.text += text;
          renderChatThread();
        },
        onDone: (done) => {
          clearTimeout(stallTimer);
          message.answer.text = done.answer ?? message.answer.text;
          message.answer.warnings = done.warnings || [];
          message.streaming = false;
          renderChatThread();
        },
      },
      controller.signal
    );
    setQaStatus("Answer ready.", "success");
  } catch (error) {
    if (error.name === "AbortError") {
      setQaStatus("Stopped: no response from the backend for 30s.", "error");
    } else {
      setQaStatus(error.message, "error");
    }
    message.streaming = false;
    renderChatThread();
  } finally {
    clearTimeout(stallTimer);
    $("ask-button").disabled = state.selectedSourceIds.length === 0;
  }
}

async function bootstrap() {
  await loadBackendUrl();
  await refreshCurrentTab();
  await checkBackend();
  await loadSources();
  await resumeActiveJobIfAny();

  $("save-backend").addEventListener("click", saveBackendUrl);
  $("check-backend").addEventListener("click", checkBackend);
  $("refresh-tab").addEventListener("click", refreshCurrentTab);
  $("use-current-tab").addEventListener("click", useCurrentTab);
  $("ingest-button").addEventListener("click", async () => {
    try { await ingestCurrentWebsite(); } catch (error) { setStatus(error.message, "error"); }
  });
  $("refresh-sources").addEventListener("click", loadSources);
  $("new-chat").addEventListener("click", startNewChat);
  $("ask-button").addEventListener("click", async () => {
    try { await askQuestion(); } catch (error) { setQaStatus(error.message, "error"); }
  });
  $("question").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      $("ask-button").click();
    }
  });
}

document.addEventListener("DOMContentLoaded", bootstrap);

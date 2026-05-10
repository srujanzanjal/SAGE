const DEFAULT_BACKEND_URL = "http://localhost:8000/api/v1";
const STORAGE_KEYS = {
  backendUrl: "sageBackendUrl",
  currentTab: "sageCurrentWebsiteTab",
  sourceByUrl: "sageWebsiteSourceByUrl",
};

const state = {
  backendUrl: DEFAULT_BACKEND_URL,
  currentTab: null,
  sources: [],
  selectedSourceId: null,
};

function $(id) {
  return document.getElementById(id);
}

function setStatus(message, kind = "info") {
  const summary = $("result-summary");
  if (summary) {
    summary.textContent = message;
    summary.dataset.kind = kind;
  }
}

function setResult(payload) {
  const output = $("result-output");
  if (!output) return;
  output.textContent = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
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

function canonicalWebsiteUrl(url) {
  try {
    const parsed = new URL(url);
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return url;
  }
}

function apiRoot() {
  return state.backendUrl.replace(/\/api\/v1\/?$/, "");
}

async function requestJson(path, options = {}) {
  const response = await fetch(`${state.backendUrl}${path}`, {
    ...options,
    headers: {
      ...(options.headers || {}),
    },
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = typeof payload === "string" ? payload : payload?.detail || payload?.message || payload?.error || "Request failed";
    throw new Error(message);
  }
  return payload;
}

async function checkBackend() {
  try {
    const response = await fetch(`${apiRoot()}/health`);
    if (!response.ok) throw new Error("Backend health check failed.");
    setStatus("Backend is running.", "success");
    return true;
  } catch (error) {
    setStatus("SAGE backend is not running. Start it with: cd backend && python run.py", "error");
    setResult(error.message || "Backend unavailable.");
    return false;
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
  await chrome.storage.local.set({ [STORAGE_KEYS.currentTab]: state.currentTab });
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

function formatSourceLabel(source) {
  const title = source.title || source.original_ref || "Website source";
  return `${title} · ${source.chunks_count ?? 0} chunks`;
}

function renderSourceOptions() {
  const select = $("source-select");
  select.innerHTML = "";
  const websites = state.sources.filter((s) => s.source_type === "website");
  state.sources = websites;
  if (!websites.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No website sources available";
    select.append(option);
    $("sources-list").innerHTML = '<div class="source-item"><div class="source-title">No website sources yet</div><div class="source-meta">Crawl a website first.</div></div>';
    return;
  }
  if (!state.selectedSourceId || !websites.some((s) => s.source_id === state.selectedSourceId)) {
    state.selectedSourceId = websites[0].source_id;
  }
  for (const source of websites) {
    const option = document.createElement("option");
    option.value = source.source_id;
    option.textContent = formatSourceLabel(source);
    select.append(option);
  }
  select.value = state.selectedSourceId;
  renderSourceCards();
}

function renderSourceCards() {
  const container = $("sources-list");
  container.innerHTML = "";
  for (const source of state.sources) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `source-item ${source.source_id === state.selectedSourceId ? "selected" : ""}`;
    card.addEventListener("click", () => {
      state.selectedSourceId = source.source_id;
      $("source-select").value = source.source_id;
      renderSourceCards();
    });
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
    card.append(title, meta, tags);
    container.append(card);
  }
}

async function loadSources() {
  try {
    setStatus("Loading website sources...", "info");
    const payload = await requestJson("/sources");
    state.sources = Array.isArray(payload) ? payload.filter((s) => s.source_type === "website") : [];
    renderSourceOptions();
    setStatus(`Loaded ${state.sources.length} website source${state.sources.length === 1 ? "" : "s"}.`, "success");
  } catch (error) {
    setStatus(error.message || "Failed to load sources.", "error");
    setResult(error.message || "Failed to load sources.");
  }
}

async function pollJob(jobId) {
  for (;;) {
    const job = await requestJson(`/jobs/${jobId}`);
    setStatus(job.message || `Job ${job.status}`, job.status === "failed" ? "error" : "info");
    if (job.status === "completed" || job.status === "failed") return job;
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}

async function rememberSourceForUrl(url, result) {
  const key = canonicalWebsiteUrl(url);
  const existing = await chrome.storage.local.get([STORAGE_KEYS.sourceByUrl]);
  const map = existing[STORAGE_KEYS.sourceByUrl] || {};
  map[key] = { url: key, result, updatedAt: new Date().toISOString() };
  await chrome.storage.local.set({ [STORAGE_KEYS.sourceByUrl]: map });
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
    let result = await requestJson("/jobs/website-ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: sourceUrl, max_pages: maxPages, max_depth: maxDepth }),
    });
    result = await pollJob(result.job_id);
    await rememberSourceForUrl(sourceUrl, result);
    await loadSources();
    setStatus(result.status === "failed" ? "Website crawl failed." : "Website crawl complete.", result.status === "failed" ? "error" : "success");
    setResult(result);
  } finally {
    $("ingest-button").disabled = false;
  }
}

function getSelectedSource() {
  return state.sources.find((source) => source.source_id === state.selectedSourceId) || null;
}

async function askQuestion() {
  const selectedSource = getSelectedSource();
  const question = $("question").value.trim();
  const mode = $("qa-mode").value;
  const topK = Number($("top-k").value || 6);
  if (!selectedSource) throw new Error("Select a website source first.");
  if (!question) throw new Error("Enter a question first.");

  $("ask-button").disabled = true;
  try {
    if (!(await checkBackend())) return;
    setStatus("Asking question...", "info");
    const response = await requestJson("/qa/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        mode,
        knowledgebase_id: selectedSource.knowledgebase_id,
        source_id: selectedSource.source_id,
        top_k: topK,
      }),
    });
    setStatus("Answer ready.", "success");
    setResult(response);
  } finally {
    $("ask-button").disabled = false;
  }
}

async function bootstrap() {
  await loadBackendUrl();
  await refreshCurrentTab();
  await checkBackend();
  await loadSources();

  $("save-backend").addEventListener("click", saveBackendUrl);
  $("check-backend").addEventListener("click", checkBackend);
  $("refresh-tab").addEventListener("click", refreshCurrentTab);
  $("use-current-tab").addEventListener("click", useCurrentTab);
  $("ingest-button").addEventListener("click", async () => {
    try { await ingestCurrentWebsite(); } catch (error) { setStatus(error.message, "error"); setResult(error.message); }
  });
  $("refresh-sources").addEventListener("click", loadSources);
  $("source-select").addEventListener("change", () => { state.selectedSourceId = $("source-select").value; renderSourceCards(); });
  $("ask-button").addEventListener("click", async () => {
    try { await askQuestion(); } catch (error) { setStatus(error.message, "error"); setResult(error.message); }
  });
}

document.addEventListener("DOMContentLoaded", bootstrap);

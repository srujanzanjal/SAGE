const DEFAULT_BACKEND_URL = "http://localhost:8000/api/v1";
const STORAGE_KEYS = {
  backendUrl: "sageBackendUrl",
  currentTab: "sageCurrentWebsiteTab",
};

function detectWebsiteSupport(tab) {
  const url = tab?.url || "";
  if (!/^https?:\/\//i.test(url)) return "unsupported";
  if (/youtube\.com|youtu\.be/i.test(url)) return "main_app_video";
  if (/github\.com/i.test(url)) return "main_app_github";
  if (/\.pdf(?:[?#]|$)/i.test(url)) return "main_app_pdf";
  return "website";
}

async function getStoredBackendUrl() {
  const result = await chrome.storage.local.get([STORAGE_KEYS.backendUrl]);
  return result[STORAGE_KEYS.backendUrl] || DEFAULT_BACKEND_URL;
}

async function storeCurrentTab(tab) {
  const context = {
    tabId: tab?.id ?? null,
    url: tab?.url || "",
    title: tab?.title || "",
    sourceType: detectWebsiteSupport(tab),
    updatedAt: new Date().toISOString(),
  };
  await chrome.storage.local.set({ [STORAGE_KEYS.currentTab]: context });
  return context;
}

async function syncActiveTab() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) await storeCurrentTab(tab);
  } catch {
    // Best effort only.
  }
}

async function enableSidePanel() {
  if (chrome.sidePanel?.setPanelBehavior) {
    await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  }
}

chrome.runtime.onInstalled.addListener(async () => {
  await enableSidePanel();
  await syncActiveTab();
});

chrome.runtime.onStartup.addListener(async () => {
  await enableSidePanel();
  await syncActiveTab();
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  try {
    const tab = await chrome.tabs.get(tabId);
    await storeCurrentTab(tab);
  } catch {
    // Best effort only.
  }
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete" && !changeInfo.url) return;
  try {
    await storeCurrentTab(tab || { id: tabId, url: changeInfo.url || "", title: tab?.title || "" });
  } catch {
    // Best effort only.
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "SAGE_SYNC_TAB") {
    storeCurrentTab(message.tab)
      .then((context) => sendResponse({ ok: true, context }))
      .catch((error) => sendResponse({ ok: false, error: error?.message || "Failed to sync tab" }));
    return true;
  }

  if (message?.type === "SAGE_GET_BACKEND_URL") {
    getStoredBackendUrl()
      .then((backendUrl) => sendResponse({ ok: true, backendUrl }))
      .catch((error) => sendResponse({ ok: false, error: error?.message || "Failed to read backend URL" }));
    return true;
  }

  return false;
});

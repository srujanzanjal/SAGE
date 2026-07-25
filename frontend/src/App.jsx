import { ArrowLeft, BrainCircuit } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import ChatPanel from "./components/ChatPanel";
import LandingPage from "./components/LandingPage";
import SourceIngestPanel from "./components/SourceIngestPanel";
import SourceList from "./components/SourceList";
import SummaryCard from "./components/SummaryCard";
import { deleteKnowledgebase, deleteSource, getJobStatus, listSources, recrawlWebsite } from "./lib/api";

const MODULES = {
  website: {
    label: "Website Intelligence",
    subtitle: "Playwright crawl mode with grounded citations and crawl progress.",
  },
  pdf: {
    label: "PDF / Document Intelligence",
    subtitle: "Upload PDFs and query indexed pages with grounded answers.",
  },
  video: {
    label: "YouTube / Video Transcript Intelligence",
    subtitle: "Ingest transcripts and ask questions with timestamp citations.",
  },
  github: {
    label: "GitHub Repository Intelligence",
    subtitle: "Analyze public repos with file-path, line-range, and code citations.",
  },
};

export default function App() {
  const [sources, setSources] = useState([]);
  const [selectedSource, setSelectedSource] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [selectedType, setSelectedType] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const unmountedRef = useRef(false);

  useEffect(() => () => {
    unmountedRef.current = true;
  }, []);

  const filteredSources = useMemo(
    () => sources.filter((source) => source.source_type === selectedType),
    [sources, selectedType],
  );

  const currentModule = selectedType ? MODULES[selectedType] : null;

  async function refreshSources() {
    try {
      setLoadError(null);
      const data = await listSources();
      setSources(data);
    } catch (error) {
      setLoadError(error.message);
    }
  }

  useEffect(() => {
    refreshSources();
  }, []);

  useEffect(() => {
    if (!selectedType) {
      setSelectedSource(null);
      return;
    }
    if (selectedSource?.source_type !== selectedType) {
      setSelectedSource(filteredSources[0] || null);
    }
  }, [selectedType, filteredSources, selectedSource]);

  function handleIngested(result) {
    const createdSources = result.sources_created
      ? result.sources_created.map((source) => ({
          knowledgebase_id: source.knowledgebase_id,
          knowledgebase_name: source.knowledgebase_name,
          source_id: source.source_id,
          source_type: source.source_type,
          title: source.title,
          canonical_ref: source.canonical_ref,
          original_ref: source.canonical_ref,
          status: source.status,
          chunks_count: source.chunks_count,
          page_count: source.page_count,
          crawled_pages: source.crawled_pages,
          transcript_duration: source.transcript_duration,
          video_id: source.video_id,
          repo_owner: source.repo_owner,
          repo_name: source.repo_name,
          branch: source.branch,
          detected_languages: source.detected_languages,
          files_indexed: source.files_indexed,
          files_skipped: source.files_skipped,
          meta: {
            ...(source.meta || {}),
            repo_owner: source.repo_owner,
            repo_name: source.repo_name,
            branch: source.branch,
            detected_languages: source.detected_languages,
            files_indexed: source.files_indexed,
            files_skipped: source.files_skipped,
          },
        }))
      : [
          {
            knowledgebase_id: result.knowledgebase_id,
            knowledgebase_name: result.knowledgebase_name,
            source_id: result.source_id,
            source_type: result.source_type,
            title: result.title,
            canonical_ref: result.canonical_ref,
            original_ref: result.canonical_ref,
            status: result.status,
            chunks_count: result.chunks_count,
            page_count: result.page_count,
            crawled_pages: result.crawled_pages,
            transcript_duration: result.transcript_duration,
            video_id: result.video_id,
            repo_owner: result.repo_owner,
            repo_name: result.repo_name,
            branch: result.branch,
            detected_languages: result.detected_languages,
            files_indexed: result.files_indexed,
            files_skipped: result.files_skipped,
            meta: {
              ...(result.meta || {}),
              repo_owner: result.repo_owner,
              repo_name: result.repo_name,
              branch: result.branch,
              detected_languages: result.detected_languages,
              files_indexed: result.files_indexed,
              files_skipped: result.files_skipped,
            },
          },
        ];

    setSources((previous) => {
      const updated = [...previous];
      for (const source of createdSources) {
        const index = updated.findIndex((item) => item.source_id === source.source_id);
        if (index >= 0) {
          updated[index] = source;
        } else {
          updated.unshift(source);
        }
      }
      return updated;
    });

    if (createdSources.length > 0) {
      setSelectedSource(createdSources[0]);
      setSelectedType(createdSources[0].source_type);
    }
  }

  async function handleDeleteSource(source) {
    if (!source || !window.confirm(`Delete source "${source.title || source.original_ref}"?`)) {
      return;
    }
    setActionLoading(true);
    setActionMessage(null);
    try {
      await deleteSource(source.source_id);
      setActionMessage({ type: "success", text: "Source deleted successfully." });
      if (selectedSource?.source_id === source.source_id) {
        setSelectedSource(null);
      }
      await refreshSources();
    } catch (error) {
      setActionMessage({ type: "error", text: error.message });
    } finally {
      setActionLoading(false);
    }
  }

  async function handleDeleteKnowledgebase(source) {
    if (!source || !window.confirm(`Delete knowledgebase for "${source.title || source.original_ref}"? This removes all related sources.`)) {
      return;
    }
    setActionLoading(true);
    setActionMessage(null);
    try {
      await deleteKnowledgebase(source.knowledgebase_id);
      setActionMessage({ type: "success", text: "Knowledgebase deleted successfully." });
      setSelectedSource(null);
      await refreshSources();
    } catch (error) {
      setActionMessage({ type: "error", text: error.message });
    } finally {
      setActionLoading(false);
    }
  }

  async function waitForJob(jobId) {
    while (!unmountedRef.current) {
      const job = await getJobStatus(jobId);
      if (unmountedRef.current || job.status === "completed" || job.status === "failed") {
        return job;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    return null;
  }

  async function handleRecrawlSource(source) {
    if (!source || source.source_type !== "website" || !window.confirm(`Re-crawl website source "${source.title || source.original_ref}"? This will replace existing website chunks.`)) {
      return;
    }
    setActionLoading(true);
    setActionMessage({ type: "success", text: "Re-crawl started. Polling status..." });
    try {
      const job = await recrawlWebsite({ knowledgebase_id: source.knowledgebase_id, max_pages: 10, max_depth: 1 });
      const finalJob = await waitForJob(job.job_id);
      if (unmountedRef.current || !finalJob) return;
      if (finalJob.status === "completed") {
        setActionMessage({ type: "success", text: `Re-crawl complete: ${finalJob.result?.crawl_summary?.pages_successfully_ingested || 0} pages, ${finalJob.result?.crawl_summary?.total_chunks_created || 0} chunks.` });
        await refreshSources();
      } else {
        setActionMessage({ type: "error", text: finalJob.error || finalJob.message || "Re-crawl failed." });
      }
    } catch (error) {
      if (!unmountedRef.current) setActionMessage({ type: "error", text: error.message });
    } finally {
      if (!unmountedRef.current) setActionLoading(false);
    }
  }

  if (selectedType === null) {
    return <LandingPage onSelectType={setSelectedType} />;
  }

  return (
    <main className="min-h-screen px-4 py-6 text-slate-950 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="overflow-hidden rounded-[2rem] border border-slate-200/70 bg-white/80 p-5 shadow-[0_24px_80px_-48px_rgba(15,23,42,0.35)] backdrop-blur sm:p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="flex items-start gap-4">
              <div className="rounded-2xl bg-slate-950 p-3 text-white shadow-lg shadow-slate-950/20">
                <BrainCircuit size={30} />
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-indigo-600">SAGE · Source-Grounded AI</p>
                <h1 className="mt-1 text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">Semantic Analysis and Generation Engine</h1>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 sm:text-base">
                  {currentModule?.subtitle || "Choose a source, ingest it, and ask grounded questions with citations."}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 text-sm">
              <button
                type="button"
                onClick={() => setSelectedType(null)}
                className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 font-semibold text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
              >
                <ArrowLeft size={16} /> Change module
              </button>
              <span className="rounded-full bg-indigo-50 px-4 py-2 font-semibold text-indigo-700">
                {currentModule?.label || "Module"}
              </span>
            </div>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {[
              "Website crawl",
              "PDF upload",
              "Video transcript",
              "GitHub repo",
              "Confidence scoring",
              "Source citations",
            ].map((item) => (
              <div key={item} className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-center text-xs font-semibold uppercase tracking-wide text-slate-600">
                {item}
              </div>
            ))}
          </div>
        </header>

        {loadError && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            Could not load sources yet: {loadError}
          </div>
        )}

        {actionMessage && (
          <div className={`rounded-2xl px-4 py-3 text-sm shadow-sm ${actionMessage.type === "success" ? "border border-emerald-200 bg-emerald-50 text-emerald-800" : "border border-rose-200 bg-rose-50 text-rose-800"}`}>
            {actionMessage.text}
          </div>
        )}

        <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
          <div className="xl:sticky xl:top-6 xl:self-start">
            <SourceList
              sources={filteredSources}
              selectedSource={selectedSource}
              onSelect={setSelectedSource}
              onRefresh={refreshSources}
              onDeleteSource={handleDeleteSource}
              onDeleteKnowledgebase={handleDeleteKnowledgebase}
              onRecrawlSource={handleRecrawlSource}
              actionLoading={actionLoading}
            />
          </div>

          <div className="space-y-6">
            <div className="rounded-[2rem] border border-slate-200/70 bg-white/80 p-4 shadow-[0_24px_80px_-48px_rgba(15,23,42,0.35)] backdrop-blur sm:p-6">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.24em] text-indigo-600">Current module</p>
                  <h2 className="text-2xl font-black text-slate-950">{currentModule?.label}</h2>
                </div>
                {selectedSource ? (
                  <span className="rounded-full bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700">
                    Selected source: {selectedSource.title || selectedSource.original_ref}
                  </span>
                ) : (
                  <span className="rounded-full bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-600">
                    No source selected yet
                  </span>
                )}
              </div>

              <SourceIngestPanel
                sourceType={selectedType}
                onIngested={handleIngested}
                onGoBack={() => {
                  setSelectedType(null);
                  setSelectedSource(null);
                }}
              />
            </div>

            <SummaryCard source={selectedSource} />

            <ChatPanel selectedSource={selectedSource} allSources={sources} />
          </div>
        </div>
      </div>
    </main>
  );
}

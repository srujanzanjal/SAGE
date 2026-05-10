import { FileText, Globe2, Loader2, Upload, ChevronLeft, Video, GitBranch } from "lucide-react";
import { useState } from "react";
import { ApiError, getJobStatus, listSources, startPdfIngestJob, startVideoAutoTranscribeJob, startVideoIngestJob, startWebsiteIngestJob, startGithubIngestJob } from "../lib/api";

export default function SourceIngestPanel({ sourceType, onIngested, onGoBack }) {
  const [url, setUrl] = useState("");
  const [maxPages, setMaxPages] = useState(10);
  const [maxDepth, setMaxDepth] = useState(1);
  const [branch, setBranch] = useState("");
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(null);
  const [message, setMessage] = useState(null);
  const [jobState, setJobState] = useState(null);
  const [videoFallback, setVideoFallback] = useState(null);

  async function waitForJob(jobId) {
    while (true) {
      const job = await getJobStatus(jobId);
      setJobState(job);
      if (job.status === "completed" || job.status === "failed") {
        return job;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  }

  async function handleWebsiteSubmit(event) {
    event.preventDefault();
    setLoading("website");
    setMessage(null);
    setJobState(null);
    try {
      const job = await startWebsiteIngestJob(url, maxPages, maxDepth);
      const finalJob = await waitForJob(job.job_id);
      if (finalJob.status === "completed") {
        const result = finalJob.result;
        setUrl("");
        setMessage({
          type: "success",
          text: `Crawl complete: ${result.crawl_summary.pages_successfully_ingested} pages, ${result.crawl_summary.total_chunks_created} chunks created.`
        });
        onIngested(result);
      } else {
        const errorText = finalJob?.result?.message || finalJob.error || finalJob.message || "Website crawl failed.";
        setMessage({ type: "error", text: errorText });
      }
    } catch (error) {
      setMessage({ type: "error", text: error.message });
    } finally {
      setLoading(null);
    }
  }

  async function handlePdfSubmit(event) {
    event.preventDefault();
    if (!file) return;
    setLoading("pdf");
    setMessage(null);
    setJobState(null);
    try {
      const job = await startPdfIngestJob(file);
      const finalJob = await waitForJob(job.job_id);
      if (finalJob.status === "completed") {
        const result = finalJob.result;
        setFile(null);
        event.target.reset();
        setMessage({ type: "success", text: `PDF ready: ${result.chunks_count} chunks created.` });
        onIngested(result);
      } else {
        setMessage({ type: "error", text: finalJob.error || finalJob.message || "PDF ingestion failed." });
      }
    } catch (error) {
      setMessage({ type: "error", text: error.message });
    } finally {
      setLoading(null);
    }
  }

  async function handleVideoSubmit(event) {
    event.preventDefault();
    setLoading("video");
    setMessage(null);
    setJobState(null);
    setVideoFallback(null);
    // Check for existing ready source for the same video to avoid re-transcribing
    try {
      const vid = (() => {
        try {
          const u = new URL(url);
          if (u.hostname.includes("youtube")) return new URLSearchParams(u.search).get("v");
          if (u.hostname === "youtu.be") return u.pathname.replace("/", "");
        } catch {
          return null;
        }
      })();
      if (vid) {
        const sources = await listSources();
        const existing = sources.find((s) => s.source_type === "video" && (s.video_id === vid || s.original_ref?.includes(vid) || s.canonical_ref?.includes(vid)) && s.status === "ready" && (s.chunks_count || 0) > 0);
        if (existing) {
          setMessage({ type: "success", text: "This video has already been analyzed. Using existing source." });
          setUrl("");
          setLoading(null);
          onIngested({
            source_id: existing.source_id,
            source_type: existing.source_type,
            title: existing.title,
            canonical_ref: existing.canonical_ref,
            status: existing.status,
            chunks_count: existing.chunks_count,
            transcript_duration: existing.transcript_duration,
            video_id: existing.video_id,
            meta: existing.meta,
          });
          return;
        }
      }
    } catch (err) {
      // ignore preflight errors and continue to attempt ingest
    }
    try {
      const job = await startVideoIngestJob(url);
      const finalJob = await waitForJob(job.job_id);
      if (finalJob.status === "completed") {
        const result = finalJob.result;
        setUrl("");
        setMessage({
          type: "success",
          text: `Video transcript ready: ${result.chunks_count} chunks${result.transcript_duration ? `, ${Math.round(result.transcript_duration)}s transcript` : ""}.`
        });
        onIngested(result);
      } else {
        if (finalJob?.result?.error_code === "TRANSCRIPT_NOT_AVAILABLE") {
          setVideoFallback({
            url,
            message: finalJob?.result?.message || "Transcript not available from YouTube.",
            fallbackOptions: finalJob?.result?.fallback_options || ["auto_transcribe"]
          });
          setMessage({ type: "error", text: finalJob?.result?.message || "Transcript not available from YouTube." });
        } else {
          setMessage({ type: "error", text: finalJob.error || finalJob.message || "Video ingestion failed." });
        }
      }
    } catch (error) {
      if (error instanceof ApiError && error.code === "TRANSCRIPT_NOT_AVAILABLE") {
        setVideoFallback({
          url,
          message: error.message,
          fallbackOptions: error.fallbackOptions
        });
      }
      setMessage({ type: "error", text: error.message });
    } finally {
      setLoading(null);
    }
  }

  async function handleVideoAutoTranscribe(event) {
    event.preventDefault();
    const fallbackUrl = videoFallback?.url || url;
    if (!fallbackUrl) return;

    // Preflight: avoid re-transcribing if a ready source already exists
    try {
      const u = new URL(fallbackUrl);
      const vid = u.hostname.includes("youtube") ? new URLSearchParams(u.search).get("v") : u.hostname === "youtu.be" ? u.pathname.replace("/", "") : null;
      if (vid) {
        const sources = await listSources();
        const existing = sources.find((s) => s.source_type === "video" && (s.video_id === vid || s.original_ref?.includes(vid) || s.canonical_ref?.includes(vid)) && s.status === "ready" && (s.chunks_count || 0) > 0);
        if (existing) {
          setMessage({ type: "success", text: "This video has already been analyzed. Using existing source." });
          setUrl("");
          setLoading(null);
          onIngested({
            source_id: existing.source_id,
            source_type: existing.source_type,
            title: existing.title,
            canonical_ref: existing.canonical_ref,
            status: existing.status,
            chunks_count: existing.chunks_count,
            transcript_duration: existing.transcript_duration,
            video_id: existing.video_id,
            meta: existing.meta,
          });
          return;
        }
      }
    } catch (err) {
      // ignore and continue
    }

    // Clear previous error state and indicate auto-transcribe is starting
    setLoading("video_auto");
    setMessage({ type: "info", text: "Generating transcript automatically..." });
    setJobState({ current_step: "starting", progress_percentage: 1, message: "Starting auto-transcription" });
    setVideoFallback(null);

    try {
      const job = await startVideoAutoTranscribeJob(fallbackUrl);
      const finalJob = await waitForJob(job.job_id);
      if (finalJob.status === "completed") {
        const result = finalJob.result;
        setUrl("");
        setVideoFallback(null);
        setMessage({
          type: "success",
          text: `Auto-transcribed video ready: ${result.chunks_count} chunks${result.duration_seconds ? `, ${Math.round(result.duration_seconds)}s` : ""}.`
        });
        onIngested(result);
      } else {
        const errorText = finalJob?.result?.message || finalJob.error || finalJob.message || "Video auto-transcription failed.";
        setMessage({ type: "error", text: errorText });
      }
    } catch (error) {
      setMessage({ type: "error", text: error.message });
    } finally {
      setLoading(null);
    }
  }

  async function handleGithubSubmit(event) {
    event.preventDefault();
    setLoading("github");
    setMessage(null);
    setJobState(null);
    try {
      const job = await startGithubIngestJob(url, branch.trim() || null);
      const finalJob = await waitForJob(job.job_id);
      if (finalJob.status === "completed") {
        const result = finalJob.result;
        setUrl("");
        setBranch("");
        setMessage({ type: "success", text: `Repository ingested: ${result.repo_owner}/${result.repo_name}, ${result.chunks_count} chunks.` });
        onIngested(result);
      } else {
        setMessage({ type: "error", text: finalJob.error || finalJob.message || "GitHub ingestion failed." });
      }
    } catch (error) {
      setMessage({ type: "error", text: error.message });
    } finally {
      setLoading(null);
    }
  }

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">
            {sourceType === "website" ? "Website Crawl" : sourceType === "video" ? "Video Transcript" : sourceType === "github" ? "GitHub Repository" : "PDF Upload"}
          </p>
          <h2 className="text-2xl font-bold text-slate-950">
            {sourceType === "website"
              ? "Crawl and analyze a website"
              : sourceType === "video"
                ? "Ingest and analyze a YouTube video"
                : sourceType === "github"
                  ? "Ingest and analyze a public GitHub repository"
                  : "Upload a PDF document"}
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            {sourceType === "website"
              ? "SAGE will crawl internal links, extract content, chunk it, embed it, and index it."
              : sourceType === "video"
                ? "SAGE will fetch the transcript, chunk it with timestamps, embed it, and index it."
                : sourceType === "github"
                  ? "SAGE will fetch the repository, scan source files, chunk them by line ranges, and index them."
                  : "SAGE will extract, chunk, embed, and index your PDF."}
          </p>
        </div>
        <button
          onClick={onGoBack}
          className="flex items-center gap-2 text-sm font-semibold text-slate-600 hover:text-slate-950 transition"
        >
          <ChevronLeft size={16} /> Go Back
        </button>
      </div>

      {sourceType === "website" ? (
        <form onSubmit={handleWebsiteSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-semibold text-slate-800 mb-2">Website URL</label>
            <input
              type="url"
              required
              placeholder="https://example.com"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:border-indigo-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-semibold text-slate-800 mb-2">Max Pages</label>
              <input
                type="number"
                min="1"
                max="100"
                value={maxPages}
                onChange={(event) => setMaxPages(parseInt(event.target.value) || 10)}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-slate-800 mb-2">Max Depth</label>
              <input
                type="number"
                min="1"
                max="3"
                value={maxDepth}
                onChange={(event) => setMaxDepth(parseInt(event.target.value) || 1)}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:border-indigo-500"
              />
            </div>
          </div>

          <button className="w-full flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60" disabled={loading === "website"}>
            {loading === "website" ? <Loader2 className="animate-spin" size={16} /> : <Globe2 size={16} />} Start Crawl
          </button>
        </form>
      ) : sourceType === "video" ? (
        <form onSubmit={handleVideoSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-semibold text-slate-800 mb-2">YouTube URL</label>
            <input
              type="url"
              required
              placeholder="https://www.youtube.com/watch?v=..."
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:border-indigo-500"
            />
          </div>

          <button className="w-full flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60" disabled={loading === "video"}>
            {loading === "video" ? <Loader2 className="animate-spin" size={16} /> : <Video size={16} />} Ingest Transcript
          </button>

          {videoFallback && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
              <p className="text-sm font-semibold text-amber-900">Transcript not available from YouTube</p>
              <p className="mt-1 text-sm text-amber-800">
                SAGE could not access captions for this video. You can still analyze it by generating a transcript automatically using speech-to-text.
              </p>
              <p className="mt-2 text-xs text-amber-700">This may take a few minutes depending on video length.</p>
              <p className="text-xs text-amber-700">For live demos, use a pre-analyzed video or videos under 5 minutes.</p>
              <button
                type="button"
                onClick={handleVideoAutoTranscribe}
                className="mt-3 w-full flex items-center justify-center gap-2 rounded-xl bg-amber-600 px-4 py-3 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-60"
                disabled={loading === "video_auto"}
              >
                {loading === "video_auto" ? <Loader2 className="animate-spin" size={16} /> : <Video size={16} />} Generate Transcript Automatically
              </button>
            </div>
          )}
        </form>
      ) : sourceType === "github" ? (
          <form onSubmit={handleGithubSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-semibold text-slate-800 mb-2">GitHub Repository URL</label>
              <input
                type="url"
                required
                placeholder="https://github.com/owner/repo"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-slate-800 mb-2">Branch (optional)</label>
              <input
                type="text"
                placeholder="main"
                value={branch}
                onChange={(event) => setBranch(event.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:border-indigo-500"
              />
            </div>

            <button className="w-full flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60" disabled={loading === "github"}>
              {loading === "github" ? <Loader2 className="animate-spin" size={16} /> : <GitBranch size={16} />} Ingest Repository
            </button>
          </form>
      ) : (
        <form onSubmit={handlePdfSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-semibold text-slate-800 mb-2">PDF File</label>
            <input
              type="file"
              accept="application/pdf,.pdf"
              required
              onChange={(event) => setFile(event.target.files?.[0] || null)}
              className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:border-indigo-500"
            />
          </div>

          <button className="w-full flex items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60" disabled={loading === "pdf"}>
            {loading === "pdf" ? <Loader2 className="animate-spin" size={16} /> : <Upload size={16} />} Upload PDF
          </button>
        </form>
      )}

      {message && (
        <div className={`mt-4 rounded-2xl px-4 py-3 text-sm ${message.type === "success" ? "bg-emerald-50 text-emerald-700" : message.type === "info" ? "bg-sky-50 text-sky-700" : "bg-rose-50 text-rose-700"}`}>
          {message.text}
        </div>
      )}

      {jobState && (
        <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div className="mb-2 flex items-center justify-between gap-3 text-sm">
            <span className="font-semibold text-slate-800">{jobState.current_step}</span>
            <span className="text-slate-500">{jobState.progress_percentage}%</span>
          </div>
          <div className="h-2 rounded-full bg-slate-200">
            <div className="h-2 rounded-full bg-indigo-600 transition-all" style={{ width: `${jobState.progress_percentage}%` }} />
          </div>
          <p className="mt-2 text-xs text-slate-600">{jobState.message}</p>
          {jobState.error && <p className="mt-2 text-xs text-rose-700">{jobState.error}</p>}
        </div>
      )}
    </section>
  );
}

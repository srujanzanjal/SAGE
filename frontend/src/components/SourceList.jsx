import { Database, FileText, Globe2, Video, RefreshCw, Layers, Trash2, RotateCcw, Info, GitBranch, Hash } from "lucide-react";

export default function SourceList({ sources, selectedSource, onSelect, onRefresh, onDeleteSource, onDeleteKnowledgebase, onRecrawlSource, actionLoading }) {
  const getSourceIcon = (type) => (type === "pdf" ? FileText : type === "video" ? Video : type === "github" ? GitBranch : Globe2);
  
  const getStatusBadge = (status) => {
    const colors = {
      ready: "bg-emerald-50 text-emerald-700",
      failed: "bg-rose-50 text-rose-700",
      processing: "bg-blue-50 text-blue-700"
    };
    return colors[status] || colors.ready;
  };

  const getTypeLabel = (type) => (type === "pdf" ? "PDF" : type === "video" ? "Video" : type === "github" ? "GitHub Repo" : "Website");

  const formatDuration = (seconds) => {
    if (seconds === undefined || seconds === null || Number.isNaN(Number(seconds))) return null;
    const total = Math.max(0, Math.round(Number(seconds)));
    const minutes = Math.floor(total / 60);
    const remaining = total % 60;
    return `${minutes}:${String(remaining).padStart(2, "0")}`;
  };

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">Sources</p>
          <h2 className="text-xl font-bold text-slate-950">Ingested sources</h2>
        </div>
        <button onClick={onRefresh} className="rounded-xl border border-slate-200 p-2 text-slate-600 hover:bg-slate-50" title="Refresh">
          <RefreshCw size={17} />
        </button>
      </div>

      {sources.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
          <Database className="mx-auto mb-2" size={26} />
          No sources yet. Ingest a website, GitHub repo, video, or PDF first.
        </div>
      ) : (
        <div className="space-y-3">
          {sources.map((source) => {
            const active = selectedSource?.source_id === source.source_id;
            const Icon = getSourceIcon(source.source_type);
            return (
              <button
                key={source.source_id}
                onClick={() => onSelect(source)}
                className={`w-full rounded-2xl border p-4 text-left transition ${active ? "border-indigo-500 bg-indigo-50" : "border-slate-200 bg-white hover:bg-slate-50"}`}
              >
                <div className="flex items-start gap-3">
                  <div className={`rounded-xl p-2 ${active ? "bg-indigo-100 text-indigo-700" : "bg-slate-100 text-slate-600"}`}>
                    <Icon size={18} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold text-slate-900">{source.title || source.original_ref}</p>
                    <p className="truncate text-xs text-slate-500">{source.canonical_ref}</p>
                    {source.knowledgebase_name && (
                      <p className="truncate text-[11px] text-slate-400">KB: {source.knowledgebase_name}</p>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      <span className="rounded-full bg-slate-100 px-2 py-1 text-slate-600">{getTypeLabel(source.source_type)}</span>
                      <span className={`rounded-full px-2 py-1 ${getStatusBadge(source.status)}`}>{source.status}</span>
                      {source.chunks_count && (
                        <span className="flex items-center gap-1 rounded-full bg-purple-50 px-2 py-1 text-purple-700">
                          <Layers size={12} /> {source.chunks_count} chunks
                        </span>
                      )}
                      {source.source_type === "video" && source.transcript_duration ? (
                        <span className="rounded-full bg-emerald-50 px-2 py-1 text-emerald-700">
                          {formatDuration(source.transcript_duration)} transcript
                        </span>
                      ) : null}
                      {source.source_type === "video" && source.transcript_origin === "auto_transcribed" ? (
                        <span className="rounded-full bg-amber-50 px-2 py-1 text-amber-700">Auto-transcribed</span>
                      ) : null}
                      {source.source_type === "github" && (source.branch || source.meta?.branch) ? (
                        <span className="rounded-full bg-slate-100 px-2 py-1 text-slate-700">
                          branch: {source.branch || source.meta?.branch}
                        </span>
                      ) : null}
                      {source.source_type === "github" && Array.isArray(source.meta?.detected_languages) ? (
                        <span className="rounded-full bg-indigo-50 px-2 py-1 text-indigo-700">
                          {source.meta.detected_languages.slice(0, 2).join(", ")}
                        </span>
                      ) : null}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {selectedSource && (
        <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800">
            <Info size={16} className="text-indigo-600" />
            Source details
          </div>
          <div className="space-y-2 text-sm text-slate-700">
            <p><span className="font-semibold">Title:</span> {selectedSource.title || selectedSource.original_ref}</p>
            <p><span className="font-semibold">Type:</span> {getTypeLabel(selectedSource.source_type)}</p>
            <p><span className="font-semibold">Status:</span> {selectedSource.status}</p>
            <p><span className="font-semibold">Chunks:</span> {selectedSource.chunks_count || 0}</p>
            {selectedSource.page_count ? <p><span className="font-semibold">Pages:</span> {selectedSource.page_count}</p> : null}
            {selectedSource.crawled_pages ? <p><span className="font-semibold">Crawled pages:</span> {selectedSource.crawled_pages}</p> : null}
            {selectedSource.transcript_duration ? <p><span className="font-semibold">Transcript duration:</span> {formatDuration(selectedSource.transcript_duration)}</p> : null}
            {selectedSource.video_id ? <p><span className="font-semibold">Video ID:</span> {selectedSource.video_id}</p> : null}
            {selectedSource.transcript_origin ? <p><span className="font-semibold">Transcript origin:</span> {selectedSource.transcript_origin}</p> : null}
            {selectedSource.source_type === "github" && (selectedSource.branch || selectedSource.meta?.branch) ? <p><span className="font-semibold">Branch:</span> {selectedSource.branch || selectedSource.meta?.branch}</p> : null}
            {selectedSource.source_type === "github" && (selectedSource.repo_owner || selectedSource.meta?.repo_owner) ? <p><span className="font-semibold">Repository:</span> {selectedSource.repo_owner || selectedSource.meta?.repo_owner}/{selectedSource.repo_name || selectedSource.meta?.repo_name}</p> : null}
            {selectedSource.source_type === "github" && Array.isArray(selectedSource.meta?.detected_languages) ? <p><span className="font-semibold">Languages:</span> {selectedSource.meta.detected_languages.join(", ")}</p> : null}
            {selectedSource.source_type === "github" && selectedSource.files_indexed !== undefined ? <p><span className="font-semibold">Files indexed:</span> {selectedSource.files_indexed}</p> : null}
            {selectedSource.source_type === "github" && selectedSource.files_skipped !== undefined ? <p><span className="font-semibold">Files skipped:</span> {selectedSource.files_skipped}</p> : null}
            {selectedSource.created_at ? <p><span className="font-semibold">Created:</span> {new Date(selectedSource.created_at).toLocaleString()}</p> : null}
            <p className="break-all"><span className="font-semibold">Knowledgebase:</span> {selectedSource.knowledgebase_id}</p>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              disabled={actionLoading}
              onClick={() => onDeleteSource?.(selectedSource)}
              className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-white px-3 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50"
            >
              <Trash2 size={15} /> Delete Source
            </button>
            <button
              disabled={actionLoading}
              onClick={() => onDeleteKnowledgebase?.(selectedSource)}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50"
            >
              <Trash2 size={15} /> Delete Knowledgebase
            </button>
            {selectedSource.source_type === "website" && (
              <button
                disabled={actionLoading}
                onClick={() => onRecrawlSource?.(selectedSource)}
                className="inline-flex items-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-100 disabled:opacity-50"
              >
                <RotateCcw size={15} /> Re-crawl
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

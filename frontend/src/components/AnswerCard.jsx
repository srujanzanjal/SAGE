import { BadgeCheck, Quote, AlertCircle, FileText, Globe2, Copy, Video, GitBranch, Code2 } from "lucide-react";
import { useState } from "react";

function getConfidenceBadgeColor(score) {
  if (score == null) return "bg-slate-50 text-slate-500 border-slate-200";
  if (score >= 0.7) return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (score >= 0.4) return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-rose-50 text-rose-700 border-rose-200";
}

function getConfidenceLabel(score) {
  if (score == null) return "Unknown";
  if (score >= 0.7) return "High";
  if (score >= 0.4) return "Medium";
  return "Low";
}

export default function AnswerCard({ answer, streaming = false, onAskFollowUp = null }) {
  const [copyMessage, setCopyMessage] = useState(null);

  if (!answer) return null;

  const hasConfidenceScore = typeof answer.confidence_score === "number";
  const confidenceLabel = getConfidenceLabel(answer.confidence_score);
  const confidencePercent = hasConfidenceScore ? Math.round(answer.confidence_score * 100) : null;
  const showLowConfidenceWarning = hasConfidenceScore && answer.confidence_score < 0.4;

  async function copyAnswer() {
    try {
      await navigator.clipboard.writeText(answer.answer || "");
      setCopyMessage("Copied");
      setTimeout(() => setCopyMessage(null), 1500);
    } catch {
      setCopyMessage("Copy failed");
    }
  }

  return (
    <div className="mt-5 space-y-4">
      <article className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">SAGE Answer</p>
            <h3 className="text-xl font-bold text-slate-950">
              {answer.mode === "grounded" ? "Grounded Response" : "Exploratory Response"}
            </h3>
          </div>
          <div className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-sm font-semibold ${getConfidenceBadgeColor(answer.confidence_score)}`}>
            <BadgeCheck size={16} />
            <span>{confidenceLabel} Confidence</span>
            {confidencePercent !== null && <span className="text-xs font-normal">({confidencePercent}%)</span>}
          </div>
        </div>

        <div className="mb-4 flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700 font-medium">
            {answer.mode === "grounded" ? "🔒 Grounded" : "🔓 Exploratory"}
          </span>
          {answer.question && (
            <span className="rounded-full bg-indigo-50 px-3 py-1 text-indigo-700">
              Q: {answer.question.substring(0, 40)}{answer.question.length > 40 ? "..." : ""}
            </span>
          )}
        </div>

        <div className="whitespace-pre-wrap leading-7 text-slate-800 mb-4">
          {answer.answer}
          {streaming && <span className="ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 animate-pulse bg-indigo-500" aria-hidden="true" />}
        </div>

        {answer.follow_up_question && (
          <div className="mb-4 rounded-2xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-900">
            <p className="font-semibold">Suggested follow-up</p>
            {onAskFollowUp ? (
              <button
                type="button"
                onClick={() => onAskFollowUp(answer.follow_up_question)}
                className="mt-1 text-left underline decoration-dotted underline-offset-2 hover:text-indigo-700"
              >
                {answer.follow_up_question}
              </button>
            ) : (
              <p className="mt-1">{answer.follow_up_question}</p>
            )}
          </div>
        )}

        <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">Retrieved chunks: {answer.retrieved_sources?.length || 0}</span>
          {answer.retrieved_source_count !== undefined && (
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">Sources: {answer.retrieved_source_count}</span>
          )}
          <span className="rounded-full bg-indigo-50 px-3 py-1 text-indigo-700">Reason: {answer.confidence_reason}</span>
          <button onClick={copyAnswer} className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-3 py-1 text-slate-700 hover:bg-slate-50">
            <Copy size={12} /> Copy answer
          </button>
          {copyMessage && <span className="text-slate-500">{copyMessage}</span>}
        </div>

        {showLowConfidenceWarning && (
          <div className="rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 flex gap-3 text-sm text-amber-800">
            <AlertCircle size={16} className="flex-shrink-0 mt-0.5" />
            <span>No strong evidence found. The retrieved source evidence may be weak.</span>
          </div>
        )}

        {answer.warnings?.length > 0 && (
          <div className="mt-3 rounded-xl bg-blue-50 border border-blue-200 px-4 py-3 text-sm text-blue-800">
            <p className="font-medium mb-1">Warnings:</p>
            {answer.warnings.map((w, idx) => (
              <p key={idx}>• {w}</p>
            ))}
          </div>
        )}
      </article>

      {answer.citations && answer.citations.length > 0 && (
        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <Quote size={18} className="text-indigo-600" />
            <h3 className="text-lg font-bold text-slate-950">Citations and Sources</h3>
            <span className="ml-auto text-xs font-semibold text-slate-500">
              {answer.citations.length} source{answer.citations.length !== 1 ? "s" : ""}
            </span>
          </div>

          <div className="grid gap-3">
            {answer.citations.map((citation, idx) => (
              <div key={citation.citation_id ?? idx} className="rounded-2xl bg-gradient-to-br from-slate-50 to-slate-100 border border-slate-200 p-4 hover:border-slate-300 transition">
                {/* Citation Header */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center justify-center w-6 h-6 rounded-lg bg-indigo-600 text-white text-xs font-bold">
                      {citation.citation_id ? citation.citation_id.replace("[", "").replace("]", "") : idx + 1}
                    </span>
                    {typeof citation.score === "number" && (
                      <span className="text-xs font-semibold text-slate-500 uppercase">
                        Retrieval score {(citation.score * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                </div>

                {/* Source Info */}
                <div className="mb-3 flex flex-col gap-2">
                  <div className="flex items-center gap-2 text-sm">
                    {citation.source_type === "pdf" ? (
                      <FileText size={14} className="text-purple-600" />
                    ) : citation.source_type === "video" ? (
                      <Video size={14} className="text-emerald-600" />
                    ) : citation.source_type === "github" ? (
                      <GitBranch size={14} className="text-slate-700" />
                    ) : (
                      <Globe2 size={14} className="text-blue-600" />
                    )}
                    <span className="font-medium text-slate-800 break-all">{citation.source_title || citation.source_ref}</span>
                  </div>
                  {citation.source_type === "github" && (
                    <div className="ml-6 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                      {citation.source_ref && (
                        <a
                          href={citation.source_ref}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-full bg-slate-100 px-2 py-1 text-slate-700 hover:bg-slate-200"
                        >
                          Open repo
                        </a>
                      )}
                      {citation.repo_owner && citation.repo_name && citation.start_line !== undefined && citation.end_line !== undefined && (
                        <span className="rounded-full bg-indigo-50 px-2 py-1 text-indigo-700">
                          {citation.repo_owner}/{citation.repo_name} · {citation.start_line}-{citation.end_line}
                        </span>
                      )}
                    </div>
                  )}
                  {citation.source_type === "video" && citation.timestamp_label ? (
                    <div className="ml-6 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                      <span className="rounded-full bg-emerald-50 px-2 py-1 text-emerald-700">{citation.timestamp_label}</span>
                      {citation.video_id && citation.start_time !== undefined && citation.start_time !== null && (
                        <a
                          href={`https://www.youtube.com/watch?v=${citation.video_id}&t=${Math.max(0, Math.floor(Number(citation.start_time)))}s`}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-full bg-slate-100 px-2 py-1 text-slate-700 hover:bg-slate-200"
                        >
                          Open at timestamp
                        </a>
                      )}
                    </div>
                  ) : citation.page_number && (
                    <p className="text-xs text-slate-600 ml-6">
                      📄 Page {citation.page_number} · Chunk {citation.chunk_index || 0}
                    </p>
                  )}
                </div>

                {citation.source_type === "github" && citation.file_path && (
                  <div className="mb-3 ml-6 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <Code2 size={13} className="text-slate-500" />
                      <span className="font-semibold">{citation.file_path}</span>
                      {citation.language && <span className="rounded-full bg-white px-2 py-0.5 text-slate-600">{citation.language}</span>}
                      {citation.start_line !== undefined && citation.end_line !== undefined && (
                        <span className="rounded-full bg-white px-2 py-0.5 text-slate-600">Lines {citation.start_line}-{citation.end_line}</span>
                      )}
                    </div>
                      {citation.file_url && (
                      <a
                          href={citation.file_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex rounded-full bg-slate-900 px-3 py-1 text-white hover:bg-slate-700"
                      >
                        Open file at lines
                      </a>
                    )}
                  </div>
                )}

                <details className="rounded-xl bg-white p-3 border border-slate-200">
                  <summary className="cursor-pointer text-sm font-semibold text-slate-700">View snippet</summary>
                  <p className="mt-2 text-sm leading-6 text-slate-700">
                    {citation.snippet}
                  </p>
                </details>
              </div>
            ))}
          </div>
        </section>
      )}

      {!(answer.citations && answer.citations.length > 0) && (
        answer.retrieved_sources && answer.retrieved_sources.length > 0 ? (
          <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-4 flex items-center gap-2">
              <Quote size={18} className="text-indigo-600" />
              <h3 className="text-lg font-bold text-slate-950">Retrieved Evidence (no formal citations)</h3>
              <span className="ml-auto text-xs font-semibold text-slate-500">{answer.retrieved_sources.length} chunks</span>
            </div>
            <div className="grid gap-3">
              {answer.retrieved_sources.map((r, idx) => (
                <div key={idx} className="rounded-2xl bg-gradient-to-br from-slate-50 to-slate-100 border border-slate-200 p-4">
                  <div className="flex items-center gap-2 text-sm mb-2">
                    <Video size={14} className="text-emerald-600" />
                    <span className="font-medium text-slate-800">{r.source_title || r.source_ref}</span>
                  </div>
                  {r.timestamp_label && (
                    <div className="ml-6 flex items-center gap-2 text-xs text-slate-600 mb-2">
                      <span className="rounded-full bg-emerald-50 px-2 py-1 text-emerald-700">{r.timestamp_label}</span>
                      {r.video_id && r.start_time !== undefined && (
                        <a href={`https://www.youtube.com/watch?v=${r.video_id}&t=${Math.max(0, Math.floor(Number(r.start_time)))}s`} target="_blank" rel="noreferrer" className="rounded-full bg-slate-100 px-2 py-1 text-slate-700 hover:bg-slate-200">Open at timestamp</a>
                      )}
                    </div>
                  )}
                  <div className="ml-6 text-sm text-slate-700">{r.snippet}</div>
                </div>
              ))}
            </div>
          </section>
        ) : (
          <section className="rounded-3xl border border-dashed border-slate-200 bg-white p-6 text-sm text-slate-500 shadow-sm">No citations found.</section>
        )
      )}
    </div>
  );
}

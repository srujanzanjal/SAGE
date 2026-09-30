import { BadgeCheck, Quote, AlertCircle, FileText, Globe2, Copy, Video, GitBranch, Code2, ChevronDown, Highlighter, Loader2 } from "lucide-react";
import { Fragment, useEffect, useId, useRef, useState } from "react";
import { getEvidence } from "../lib/api";

const INLINE_PATTERN = /(\*\*[^*]+\*\*|`[^`]+`|\[S\d+\]|【S\d+】)/g;
const LIST_ITEM = /^\s*(?:[-*•]|\d+[.)])\s+/;

// Minimal markdown for LLM answers: paragraphs, bullet/numbered lists,
// headings, **bold**, `code`, and [S1] citation markers as clickable chips.
function renderInline(text, onCite) {
  return text.split(INLINE_PATTERN).map((part, i) => {
    if (!part) return null;
    const cite = part.match(/^(?:\[|【)(S\d+)(?:\]|】)$/);
    if (cite) {
      return (
        <button
          key={i}
          type="button"
          onClick={() => onCite(cite[1])}
          className="mx-0.5 inline-flex -translate-y-px items-center rounded-md bg-indigo-100 px-1.5 text-[11px] font-bold text-indigo-700 hover:bg-indigo-200"
          title={`Jump to source ${cite[1]}`}
        >
          {cite[1]}
        </button>
      );
    }
    if (part.startsWith("**")) return <strong key={i} className="font-semibold text-slate-950">{part.slice(2, -2)}</strong>;
    if (part.startsWith("`")) return <code key={i} className="rounded bg-slate-100 px-1 py-0.5 text-[0.9em]">{part.slice(1, -1)}</code>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

function AnswerText({ text, onCite }) {
  const blocks = [];
  for (const line of text.split("\n")) {
    const last = blocks[blocks.length - 1];
    if (!line.trim()) {
      blocks.push({ type: "gap" });
    } else if (LIST_ITEM.test(line)) {
      const ordered = /^\s*\d/.test(line);
      const item = line.replace(LIST_ITEM, "");
      if (last?.type === "list" && last.ordered === ordered) last.items.push(item);
      else blocks.push({ type: "list", ordered, items: [item] });
    } else if (/^#{1,6}\s/.test(line)) {
      blocks.push({ type: "heading", text: line.replace(/^#+\s*/, "") });
    } else if (last?.type === "p") {
      last.lines.push(line);
    } else {
      blocks.push({ type: "p", lines: [line] });
    }
  }
  return blocks.map((block, i) => {
    if (block.type === "gap") return null;
    if (block.type === "heading") return <p key={i} className="mt-3 font-bold text-slate-950">{renderInline(block.text, onCite)}</p>;
    if (block.type === "list") {
      const List = block.ordered ? "ol" : "ul";
      return (
        <List key={i} className={`my-2 space-y-1 pl-5 ${block.ordered ? "list-decimal" : "list-disc"}`}>
          {block.items.map((item, j) => <li key={j}>{renderInline(item, onCite)}</li>)}
        </List>
      );
    }
    return <p key={i} className="my-2 first:mt-0">{block.lines.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{renderInline(l, onCite)}</Fragment>)}</p>;
  });
}

// The answer sentences that cite this source, i.e. the claims to find evidence for.
function claimsFor(answerText, citationId) {
  const cites = new RegExp(`\\b${citationId}\\b`);
  const sentences = answerText.split(/(?<=[.!?।])\s+|\n+/).filter((s) => cites.test(s));
  return sentences.length ? sentences : [answerText.slice(0, 600)];
}

// The cited passage with the sentences that support the answer highlighted.
function EvidenceView({ citation, answerText, autoOpen }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const markRef = useRef(null);

  useEffect(() => {
    if (autoOpen) setOpen(true);
  }, [autoOpen]);

  useEffect(() => {
    if (!open || data || error) return;
    getEvidence(citation.chunk_id, claimsFor(answerText, citation.citation_id))
      .then(setData)
      .catch((err) => setError(err.message));
  }, [open]);

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "nearest" });
  }, [data]);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:border-amber-300 hover:bg-amber-50"
      >
        <Highlighter size={14} className="text-amber-600" /> Show evidence
      </button>
    );
  }

  const parts = [];
  if (data) {
    let cursor = 0;
    data.highlights.forEach((h, i) => {
      if (h.start > cursor) parts.push(<Fragment key={`t${i}`}>{data.text.slice(cursor, h.start)}</Fragment>);
      parts.push(
        <mark key={`m${i}`} ref={i === 0 ? markRef : null} className="rounded bg-amber-200/80 px-0.5 text-slate-900">
          {data.text.slice(h.start, h.end)}
        </mark>
      );
      cursor = h.end;
    });
    parts.push(<Fragment key="end">{data.text.slice(cursor)}</Fragment>);
  }

  return (
    <div className="rounded-xl border border-amber-200 bg-white p-3">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-amber-700">
        <Highlighter size={13} /> Evidence in the source
      </p>
      {!data && !error && (
        <p className="flex items-center gap-2 text-sm text-slate-500">
          <Loader2 size={14} className="animate-spin" /> Finding the supporting sentences...
        </p>
      )}
      {error && <p className="text-sm text-rose-700">{error}</p>}
      {data && (
        <>
          {data.highlights.length === 0 && (
            <p className="mb-2 text-xs text-slate-500">No single sentence stands out; the whole passage supports the answer.</p>
          )}
          <p className="max-h-64 overflow-y-auto whitespace-pre-wrap text-sm leading-6 text-slate-600">{parts}</p>
        </>
      )}
    </div>
  );
}

// Label and colour come from the backend's calibrated confidence_label, so the
// web app, extension and paper all agree on what "High" means.
const CONFIDENCE_BADGE = {
  High: "bg-emerald-50 text-emerald-700 border-emerald-200",
  Medium: "bg-amber-50 text-amber-700 border-amber-200",
  Low: "bg-rose-50 text-rose-700 border-rose-200",
};

export default function AnswerCard({ answer, streaming = false, onAskFollowUp = null }) {
  const [copyMessage, setCopyMessage] = useState(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [evidenceFor, setEvidenceFor] = useState(null);
  const uid = useId();

  if (!answer) return null;

  // A "not in the source" reply cites nothing, so its retrieved chunks would only confuse.
  const notAvailable = /^not available in the provided source/i.test((answer.answer || "").trim());
  const citations = notAvailable ? [] : answer.citations || [];

  function jumpToCitation(citationId) {
    setSourcesOpen(true);
    setEvidenceFor(citationId);
    // Wait for the list to render before scrolling to it.
    setTimeout(() => {
      const el = document.getElementById(`${uid}-${citationId}`);
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("ring-2", "ring-indigo-400");
      setTimeout(() => el.classList.remove("ring-2", "ring-indigo-400"), 1600);
    }, 50);
  }

  const hasConfidenceScore = typeof answer.confidence_score === "number";
  const confidenceLabel = answer.confidence_label || "Unknown";
  const confidencePercent = hasConfidenceScore ? Math.round(answer.confidence_score * 100) : null;

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
          <div className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-sm font-semibold ${CONFIDENCE_BADGE[confidenceLabel] || "bg-slate-50 text-slate-500 border-slate-200"}`}>
            <BadgeCheck size={16} />
            <span>{confidenceLabel} Confidence</span>
            {confidencePercent !== null && <span className="text-xs font-normal">({confidencePercent}%)</span>}
          </div>
        </div>

        <div className="mb-4 flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700 font-medium">
            {answer.mode === "grounded" ? "🔒 Grounded" : "🔓 Exploratory"}
          </span>
        </div>

        <div className="mb-4 leading-7 text-slate-800">
          <AnswerText text={answer.answer || ""} onCite={jumpToCitation} />
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

        {!streaming && !notAvailable && answer.warnings?.length > 0 && (
          <div className="mt-3 flex gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
            <div>
              {answer.warnings.map((w, idx) => (
                <p key={idx}>{w}</p>
              ))}
            </div>
          </div>
        )}
      </article>

      {citations.length > 0 && (
        <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
          <button
            type="button"
            onClick={() => setSourcesOpen((open) => !open)}
            className="flex w-full items-center gap-2 text-left"
            aria-expanded={sourcesOpen}
          >
            <Quote size={18} className="text-indigo-600" />
            <h3 className="text-lg font-bold text-slate-950">Citations and Sources</h3>
            <span className="ml-auto text-xs font-semibold text-slate-500">
              {citations.length} source{citations.length !== 1 ? "s" : ""}
            </span>
            <ChevronDown size={18} className={`text-slate-500 transition ${sourcesOpen ? "rotate-180" : ""}`} />
          </button>

          {sourcesOpen && <div className="mt-4 grid gap-3">
            {citations.map((citation, idx) => (
              <div id={`${uid}-${citation.citation_id}`} key={citation.citation_id ?? idx} className="rounded-2xl bg-gradient-to-br from-slate-50 to-slate-100 border border-slate-200 p-4 hover:border-slate-300 transition">
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

                {streaming ? (
                  <p className="text-sm leading-6 text-slate-700">{citation.snippet}</p>
                ) : (
                  <EvidenceView citation={citation} answerText={answer.answer || ""} autoOpen={evidenceFor === citation.citation_id} />
                )}
              </div>
            ))}
          </div>}
        </section>
      )}

      {citations.length === 0 && !notAvailable && !streaming && (
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
                    {r.source_type === "video" ? <Video size={14} className="text-emerald-600" /> : r.source_type === "pdf" ? <FileText size={14} className="text-purple-600" /> : r.source_type === "github" ? <GitBranch size={14} className="text-slate-700" /> : <Globe2 size={14} className="text-blue-600" />}
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

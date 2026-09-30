import { BookOpen, ExternalLink, Lightbulb, ListTree, Loader2, MessageCircleQuestion, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { getSourceBrief } from "../lib/api";
import { citationLocator } from "../lib/citations";

function Locator({ citation }) {
  const loc = citationLocator(citation);
  if (!loc) return null;
  const className = "inline-flex shrink-0 items-center gap-1 rounded-md bg-indigo-50 px-1.5 py-0.5 text-[11px] font-semibold text-indigo-700";
  return loc.href ? (
    <a href={loc.href} target="_blank" rel="noreferrer" className={`${className} hover:bg-indigo-100`} title="Open in source">
      {loc.label} <ExternalLink size={10} />
    </a>
  ) : (
    <span className={className}>{loc.label}</span>
  );
}

function Skeleton() {
  return (
    <div className="space-y-3 animate-pulse" aria-label="Building brief">
      {[100, 92, 80, 96, 70].map((w, i) => (
        <div key={i} className="h-3 rounded bg-slate-100" style={{ width: `${w}%` }} />
      ))}
    </div>
  );
}

// A structured, cited knowledge page per source, shown before any question is asked.
export default function SourceBrief({ source, onAsk }) {
  const [brief, setBrief] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function load(refresh = false) {
    if (!source?.source_id) return () => {};
    let cancelled = false;
    setLoading(true);
    setError(null);
    if (refresh) setBrief(null);
    getSourceBrief(source.source_id, refresh)
      .then((result) => !cancelled && setBrief(result))
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }

  useEffect(() => {
    setBrief(null);
    return load();
  }, [source?.source_id]);

  if (!source) return null;

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="rounded-xl bg-indigo-50 p-2 text-indigo-600">
            <BookOpen size={16} />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">Source brief</p>
            <h3 className="text-base font-bold text-slate-950">{source.title || source.original_ref}</h3>
          </div>
        </div>
        {brief && (
          <button
            type="button"
            onClick={() => load(true)}
            disabled={loading}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-50 hover:text-slate-700 disabled:opacity-50"
            title="Regenerate brief"
            aria-label="Regenerate brief"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          </button>
        )}
      </div>

      {loading && !brief && (
        <>
          <p className="mb-3 flex items-center gap-2 text-xs text-slate-500">
            <Loader2 size={13} className="animate-spin" /> Reading the source and building its brief (first time only)...
          </p>
          <Skeleton />
        </>
      )}

      {error && !brief && (
        <div className="rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Brief unavailable right now: {error}{" "}
          <button type="button" onClick={() => load()} className="font-semibold underline">
            Retry
          </button>
        </div>
      )}

      {brief && (
        <div className="space-y-5">
          <p className="text-sm leading-6 text-slate-700">{brief.summary}</p>

          {brief.key_points.length > 0 && (
            <div>
              <p className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
                <Lightbulb size={13} /> Key points
              </p>
              <ul className="space-y-2">
                {brief.key_points.map((point, i) => (
                  <li key={i} className="flex items-start justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-800">
                    <span>{point.text}</span>
                    <Locator citation={point.citation} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {brief.sections.length > 0 && (
            <div>
              <p className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
                <ListTree size={13} /> {brief.section_label}
              </p>
              <ol className="space-y-1.5">
                {brief.sections.map((section, i) => (
                  <li key={i} className="flex items-start gap-3 border-l-2 border-indigo-100 pl-3 text-sm">
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold text-slate-900">{section.title}</p>
                      {section.detail && <p className="text-slate-600">{section.detail}</p>}
                    </div>
                    <Locator citation={section.citation} />
                  </li>
                ))}
              </ol>
            </div>
          )}

          {brief.questions.length > 0 && onAsk && (
            <div>
              <p className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
                <MessageCircleQuestion size={13} /> Ask about it
              </p>
              <div className="flex flex-wrap gap-2">
                {brief.questions.map((q) => (
                  <button
                    type="button"
                    key={q}
                    onClick={() => onAsk(q)}
                    className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-left text-xs font-medium text-slate-700 transition hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

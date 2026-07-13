import { ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { getSourceSummary } from "../lib/api";

const COLLAPSED_CHAR_LIMIT = 420;

export default function SummaryCard({ source }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    setSummary(null);
    setExpanded(false);
    if (!source?.source_id) return;
    let cancelled = false;
    setLoading(true);
    getSourceSummary(source.source_id)
      .then((result) => {
        if (!cancelled) setSummary(result?.summary || null);
      })
      .catch(() => {
        if (!cancelled) setSummary(null); // best-effort — no summary card if this fails
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [source?.source_id]);

  if (!source) return null;
  if (!loading && !summary) return null;

  const isLong = summary && summary.length > COLLAPSED_CHAR_LIMIT;
  const displayText = summary && isLong && !expanded ? `${summary.slice(0, COLLAPSED_CHAR_LIMIT).trimEnd()}...` : summary;

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <div className="rounded-xl bg-indigo-50 p-2 text-indigo-600">
          <Sparkles size={16} />
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">Summary</p>
          <h3 className="text-base font-bold text-slate-950">{source.title || source.original_ref}</h3>
        </div>
      </div>

      {loading ? (
        <div className="space-y-2 animate-pulse">
          <div className="h-3 w-full rounded bg-slate-100" />
          <div className="h-3 w-11/12 rounded bg-slate-100" />
          <div className="h-3 w-4/5 rounded bg-slate-100" />
        </div>
      ) : (
        <>
          <p className="whitespace-pre-wrap text-sm leading-6 text-slate-700">{displayText}</p>
          {isLong && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-800"
            >
              {expanded ? (
                <>
                  Show less <ChevronUp size={13} />
                </>
              ) : (
                <>
                  Show full summary <ChevronDown size={13} />
                </>
              )}
            </button>
          )}
        </>
      )}
    </section>
  );
}

import { ChevronDown, FileText, GitBranch, Globe2, Loader2, MessageSquarePlus, SendHorizonal, Video, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { askQuestionStream } from "../lib/api";
import AnswerCard from "./AnswerCard";
import ModeSelector from "./ModeSelector";

const SOURCE_ICON = { pdf: FileText, video: Video, github: GitBranch, website: Globe2 };
const MAX_HISTORY_TURNS = 6;
const STARTER_QUESTIONS = {
  website: ["What is this website about?", "Summarize the key points", "How do I contact them?"],
  pdf: ["Summarize this document", "What are the main conclusions?", "Explain it simply for a beginner"],
  video: ["What is this video about?", "List the main points with timestamps", "What is the key takeaway?"],
  github: ["What does this repo do?", "How do I run it locally?", "Explain the project structure"],
};

function SourceChip({ source, onRemove }) {
  const Icon = SOURCE_ICON[source.source_type] || Globe2;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-indigo-50 py-1 pl-2.5 pr-1.5 text-xs font-medium text-indigo-700">
      <Icon size={12} />
      <span className="max-w-[160px] truncate">{source.title || source.original_ref}</span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="rounded-full p-0.5 text-indigo-500 hover:bg-indigo-100 hover:text-indigo-800"
          aria-label={`Remove ${source.title || "source"}`}
        >
          <X size={12} />
        </button>
      )}
    </span>
  );
}

export default function ChatPanel({ selectedSource, allSources = [], askRequest = null }) {
  const [mode, setMode] = useState("grounded");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]); // [{ question, answer }]
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeIds, setActiveIds] = useState(() => (selectedSource ? [selectedSource.source_id] : []));
  const [pickerOpen, setPickerOpen] = useState(false);
  const latestRequestId = useRef(0);
  const pickerRef = useRef(null);
  const threadEndRef = useRef(null);
  const abortControllerRef = useRef(null);

  const readySources = useMemo(
    () => allSources.filter((s) => s.status === "ready" && (s.chunks_count || 0) > 0),
    [allSources]
  );
  const activeSources = useMemo(
    () => activeIds.map((id) => readySources.find((s) => s.source_id === id)).filter(Boolean),
    [activeIds, readySources]
  );

  // Picking a new source from the list resets the question to just that one;
  // the "+ combine" picker is how you build up a multi-source question from there.
  useEffect(() => {
    setActiveIds(selectedSource ? [selectedSource.source_id] : []);
  }, [selectedSource?.source_id]);

  // A new source (or a fresh pick) starts a new conversation thread.
  useEffect(() => {
    latestRequestId.current += 1;
    abortControllerRef.current?.abort();
    setMessages([]);
    setError(null);
    setLoading(false);
  }, [selectedSource?.source_id]);

  // Stop an in-flight stream if the user navigates away mid-answer.
  useEffect(() => () => abortControllerRef.current?.abort(), []);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  useEffect(() => {
    if (!pickerOpen) return;
    function handleClickOutside(event) {
      if (pickerRef.current && !pickerRef.current.contains(event.target)) setPickerOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [pickerOpen]);

  function toggleSource(sourceId) {
    setActiveIds((prev) => (prev.includes(sourceId) ? prev.filter((id) => id !== sourceId) : [...prev, sourceId]));
  }

  function startNewChat() {
    latestRequestId.current += 1;
    abortControllerRef.current?.abort();
    setMessages([]);
    setError(null);
    setLoading(false);
  }

  function updateStreamingMessage(updater) {
    setMessages((prev) => {
      if (prev.length === 0) return prev;
      const next = [...prev];
      next[next.length - 1] = updater(next[next.length - 1]);
      return next;
    });
  }

  async function submitQuestion(rawQuestion) {
    if (activeIds.length === 0 || !rawQuestion.trim()) return;
    const requestId = ++latestRequestId.current;
    const askedQuestion = rawQuestion;
    const history = messages.slice(-MAX_HISTORY_TURNS).map((m) => ({ question: m.question, answer: m.answer.answer }));
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoading(true);
    setError(null);
    setQuestion("");
    setMessages((prev) => [
      ...prev,
      { question: askedQuestion, streaming: true, answer: { answer: "", mode, question: askedQuestion, citations: [], retrieved_sources: [], warnings: [] } }
    ]);

    try {
      await askQuestionStream(
        { question: askedQuestion, mode, source_ids: activeIds, history, top_k: 6 },
        {
          signal: controller.signal,
          onMeta: (meta) => {
            if (latestRequestId.current !== requestId) return;
            updateStreamingMessage((msg) => ({ ...msg, answer: { ...msg.answer, ...meta } }));
          },
          onDelta: (text) => {
            if (latestRequestId.current !== requestId) return;
            updateStreamingMessage((msg) => ({ ...msg, answer: { ...msg.answer, answer: msg.answer.answer + text } }));
          },
          onDone: (done) => {
            if (latestRequestId.current !== requestId) return;
            updateStreamingMessage((msg) => ({
              ...msg,
              streaming: false,
              answer: { ...msg.answer, answer: done.answer ?? msg.answer.answer, warnings: done.warnings ?? [] }
            }));
          }
        }
      );
    } catch (err) {
      if (err?.name === "AbortError" || latestRequestId.current !== requestId) return;
      setError(err.message);
      updateStreamingMessage((msg) => ({ ...msg, streaming: false }));
    } finally {
      if (latestRequestId.current === requestId) setLoading(false);
    }
  }

  const sectionRef = useRef(null);
  useEffect(() => {
    if (!askRequest?.text) return;
    sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    submitQuestion(askRequest.text);
    // Only a new request should trigger this, not unrelated re-renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [askRequest?.id]);

  function handleSubmit(event) {
    event.preventDefault();
    submitQuestion(question);
  }

  return (
    <section ref={sectionRef} className="scroll-mt-6 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">Ask questions</p>
          <h2 className="text-2xl font-bold text-slate-950">Source-grounded chat</h2>
          <p className="mt-1 text-sm text-slate-600">
            {activeSources.length === 0
              ? "Select or ingest a source first."
              : activeSources.length === 1
                ? `Selected: ${activeSources[0].title || activeSources[0].original_ref}`
                : `Combining ${activeSources.length} sources for this question.`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {messages.length > 0 && (
            <button
              type="button"
              onClick={startNewChat}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
              title="Clear this conversation and start a new one"
            >
              <MessageSquarePlus size={15} /> New chat
            </button>
          )}
          <ModeSelector mode={mode} onChange={setMode} />
        </div>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        {activeSources.map((source) => (
          <SourceChip
            key={source.source_id}
            source={source}
            onRemove={() => toggleSource(source.source_id)}
          />
        ))}
        <div className="relative" ref={pickerRef}>
          <button
            type="button"
            onClick={() => setPickerOpen((open) => !open)}
            className="inline-flex items-center gap-1 rounded-full border border-dashed border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:border-indigo-300 hover:text-indigo-700"
          >
            + Combine sources <ChevronDown size={12} />
          </button>
          {pickerOpen && (
            <div className="absolute left-0 top-full z-20 mt-2 w-72 max-h-80 overflow-y-auto rounded-2xl border border-slate-200 bg-white p-2 shadow-lg">
              {readySources.length === 0 ? (
                <p className="p-3 text-xs text-slate-500">No ingested sources yet.</p>
              ) : (
                readySources.map((source) => {
                  const Icon = SOURCE_ICON[source.source_type] || Globe2;
                  const active = activeIds.includes(source.source_id);
                  return (
                    <button
                      type="button"
                      key={source.source_id}
                      onClick={() => toggleSource(source.source_id)}
                      className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-xs ${active ? "bg-indigo-50 text-indigo-700" : "hover:bg-slate-50 text-slate-700"}`}
                    >
                      <input type="checkbox" checked={active} readOnly className="pointer-events-none" />
                      <Icon size={13} className="shrink-0" />
                      <span className="min-w-0 flex-1 truncate">{source.title || source.original_ref}</span>
                    </button>
                  );
                })
              )}
            </div>
          )}
        </div>
      </div>

      {messages.length > 0 && (
        <div className="mb-4 max-h-[70vh] space-y-5 overflow-y-auto rounded-2xl bg-slate-50/60 p-3">
          {messages.map((msg, idx) => (
            <div key={idx}>
              <div className="mb-2 flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-slate-900 px-4 py-2.5 text-sm text-white">
                  {msg.question}
                </div>
              </div>
              <AnswerCard answer={msg.answer} streaming={msg.streaming} onAskFollowUp={idx === messages.length - 1 ? submitQuestion : null} />
            </div>
          ))}
          <div ref={threadEndRef} />
        </div>
      )}

      {messages.length === 0 && activeSources.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {(activeSources.length > 1
            ? ["Summarize each source", "How do these sources relate?", "What do they have in common?"]
            : STARTER_QUESTIONS[activeSources[0].source_type] || STARTER_QUESTIONS.website
          ).map((starter) => (
            <button
              type="button"
              key={starter}
              onClick={() => submitQuestion(starter)}
              disabled={loading}
              className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 disabled:opacity-60"
            >
              {starter}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={activeIds.length === 0 || loading}
          placeholder={
            messages.length > 0
              ? "Ask a follow-up..."
              : activeSources.length > 1
                ? "Ask something across all selected sources..."
                : "Ask something from the selected source..."
          }
          className="min-w-0 flex-1 rounded-2xl border border-slate-200 px-4 py-3 outline-none focus:border-indigo-500 disabled:bg-slate-100"
        />
        <button disabled={activeIds.length === 0 || loading || !question.trim()} className="flex items-center gap-2 rounded-2xl bg-indigo-600 px-5 py-3 font-semibold text-white hover:bg-indigo-700 disabled:opacity-60">
          {loading ? <Loader2 className="animate-spin" size={18} /> : <SendHorizonal size={18} />}
          Ask
        </button>
      </form>

      {loading && !messages[messages.length - 1]?.answer?.answer && (
        <div className="mt-4 flex items-center gap-2 text-sm text-slate-500">
          <Loader2 className="animate-spin" size={16} /> Thinking...
        </div>
      )}
      {error && <div className="mt-4 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
    </section>
  );
}

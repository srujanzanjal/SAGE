import { Loader2, SendHorizonal } from "lucide-react";
import { useState } from "react";
import { askQuestion } from "../lib/api";
import AnswerCard from "./AnswerCard";
import ModeSelector from "./ModeSelector";

export default function ChatPanel({ selectedSource }) {
  const [mode, setMode] = useState("grounded");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!selectedSource || !question.trim()) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const result = await askQuestion({
        question,
        mode,
        knowledgebase_id: selectedSource.knowledgebase_id,
        source_id: selectedSource.source_id,
        top_k: 6
      });
      setAnswer(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">Ask questions</p>
          <h2 className="text-2xl font-bold text-slate-950">Source-grounded chat</h2>
          <p className="mt-1 text-sm text-slate-600">
            {selectedSource ? `Selected: ${selectedSource.title || selectedSource.original_ref}` : "Select or ingest a source first."}
          </p>
        </div>
        <ModeSelector mode={mode} onChange={setMode} />
      </div>

      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={!selectedSource || loading}
          placeholder="Ask something from the selected source..."
          className="min-w-0 flex-1 rounded-2xl border border-slate-200 px-4 py-3 outline-none focus:border-indigo-500 disabled:bg-slate-100"
        />
        <button disabled={!selectedSource || loading || !question.trim()} className="flex items-center gap-2 rounded-2xl bg-indigo-600 px-5 py-3 font-semibold text-white hover:bg-indigo-700 disabled:opacity-60">
          {loading ? <Loader2 className="animate-spin" size={18} /> : <SendHorizonal size={18} />}
          Ask
        </button>
      </form>

      {error && <div className="mt-4 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      <AnswerCard answer={answer} />
    </section>
  );
}

"""SAGE evaluation: retrieval ablation, answer quality, refusals, calibration.

Usage (from backend/):
    python -m eval.run_eval --retrieval          # ablation ladder, cheap (rewrites cached)
    python -m eval.run_eval --answers            # full system answers, paced for free tiers
    python -m eval.run_eval --report             # rebuild report.md + tables.tex from cached results
    python -m eval.run_eval --retrieval --model BAAI/bge-small-en-v1.5   # compare embedders

Ground truth is evidence substrings (whitespace-normalized, case-insensitive), so
results survive re-embedding and re-ingestion. Results are cached in eval/results/
so reruns don't spend free-tier LLM quota again.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"
DEFAULT_MODEL = "all-MiniLM-L6-v2"

# Ablation ladder: each config switches on one more pipeline stage.
CONFIGS = {
    "Dense only": dict(rewrite=False, hybrid=False, extras=False),
    "+ BM25 hybrid rerank": dict(rewrite=False, hybrid=True, extras=False),
    "+ Query rewriting": dict(rewrite=True, hybrid=True, extras=False),
    "Full (+ overview/position)": dict(rewrite=True, hybrid=True, extras=True),
}
CONFIDENCE_BUCKETS = [(0.0, 0.4), (0.4, 0.6), (0.6, 0.75), (0.75, 1.01)]


# ---- scoring (pure functions, unit-tested) ------------------------------------

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def evidence_found(evidence: list[str], texts: list[str], require_all: bool = False) -> bool:
    joined = [normalize(t) for t in texts]
    hits = [any(normalize(ev) in t for t in joined) for ev in evidence]
    return all(hits) if require_all else any(hits)


def first_hit_rank(evidence: list[str], texts: list[str]) -> int | None:
    for rank, text in enumerate(texts, start=1):
        if evidence_found(evidence, [text]):
            return rank
    return None


def is_refusal(answer: str) -> bool:
    return normalize(answer).startswith("not available in the provided source")


def answer_correct(item: dict, answer: str) -> bool:
    if item["category"] == "unanswerable":
        return is_refusal(answer)
    return not is_refusal(answer) and any(normalize(k) in normalize(answer) for k in item["answer_keywords"])


# ---- helpers --------------------------------------------------------------------

def model_slug(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")


def load_json(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))


def load_eval_set() -> tuple[dict, list[dict]]:
    data = json.loads((EVAL_DIR / "eval_set.json").read_text())
    return data["sources"], data["items"]


def request_for(item: dict, sources: dict):
    from app.models.schemas import QuestionRequest

    return QuestionRequest(question=item["question"], source_ids=[sources[s] for s in item["sources"]], mode="grounded")


class CachedRewriteLLM:
    """Wraps the real LLM so each question is rewritten once across all configs and runs."""

    def __init__(self, llm, cache_path: Path):
        self.llm, self.cache_path = llm, cache_path
        self.cache = load_json(cache_path, {})

    def rewrite_query(self, question, history=None, source_titles=None):
        key = f"{question}||{'; '.join(source_titles or [])}"
        if key not in self.cache:
            self.cache[key] = self.llm.rewrite_query(question, history=history, source_titles=source_titles)
            save_json(self.cache_path, self.cache)
        return self.cache[key]


# ---- runs -----------------------------------------------------------------------

def run_retrieval(model: str) -> dict:
    from app.services.llm import get_llm_service
    from app.services.qa_pipeline import _retrieve_and_build_context
    from app.services.supabase_repo import get_supabase_repository

    sources, items = load_eval_set()
    repo = get_supabase_repository()
    llm = CachedRewriteLLM(get_llm_service(), RESULTS_DIR / "rewrites.json")
    scored = [i for i in items if i["evidence"] and not i.get("skip_retrieval")]
    results = {"model": model, "configs": {}}

    for name, flags in CONFIGS.items():
        rows, started = [], time.perf_counter()
        for item in scored:
            rc = _retrieve_and_build_context(request_for(item, sources), repo, llm, **flags)
            in_context = {c.chunk_id for c in rc.citations}
            context_texts = [c.text for c in rc.ranked_chunks if c.chunk_id in in_context]
            top_k_texts = [c.text for c in rc.ranked_chunks[: rc.effective_top_k]]
            rank = first_hit_rank(item["evidence"], context_texts)
            rows.append({
                "id": item["id"],
                "category": item["category"],
                "context_hit": evidence_found(item["evidence"], context_texts, item.get("evidence_all", False)),
                "top_k_hit": evidence_found(item["evidence"], top_k_texts, item.get("evidence_all", False)),
                "rr": 1.0 / rank if rank else 0.0,
            })
        elapsed = time.perf_counter() - started
        results["configs"][name] = {"rows": rows, "ms_per_query": 1000 * elapsed / max(len(rows), 1)}
        s = summarize_retrieval(rows)
        print(f"{name:28} context_recall={s['context_recall']:.2f} recall@k={s['recall_at_k']:.2f} mrr={s['mrr']:.2f}")

    save_json(RESULTS_DIR / f"retrieval_{model_slug(model)}.json", results)
    return results


def run_answers(model: str, pace_seconds: float, fresh: bool) -> dict:
    from app.services.qa_pipeline import answer_question

    sources, items = load_eval_set()
    path = RESULTS_DIR / f"answers_{model_slug(model)}.json"
    cache = {} if fresh else load_json(path, {})
    for n, item in enumerate(items, start=1):
        if item["id"] in cache:
            continue
        started = time.perf_counter()
        try:
            response = answer_question(request_for(item, sources))
            row = {
                "answer": response.answer,
                "confidence_score": response.confidence_score,
                "confidence_label": response.confidence_label,
                "citations": len(response.citations),
            }
        except Exception as exc:  # recorded, not fatal: rerun picks it up again
            print(f"[{n}/{len(items)}] {item['id']} ERROR {exc}")
            continue
        row["seconds"] = round(time.perf_counter() - started, 2)
        if row["answer"].startswith("SAGE's free AI quota is busy"):
            print(f"[{n}/{len(items)}] {item['id']} quota busy, will retry on next run")
            continue
        cache[item["id"]] = row
        save_json(path, cache)
        mark = "OK " if answer_correct(item, row["answer"]) else "BAD"
        print(f"[{n}/{len(items)}] {mark} {item['id']:11} {row['seconds']:5.1f}s conf={row['confidence_score']:.2f} {row['answer'][:90]!r}")
        time.sleep(pace_seconds)
    return cache


# ---- summaries & report ---------------------------------------------------------------

def summarize_retrieval(rows: list[dict]) -> dict:
    n = max(len(rows), 1)
    return {
        "n": len(rows),
        "context_recall": sum(r["context_hit"] for r in rows) / n,
        "recall_at_k": sum(r["top_k_hit"] for r in rows) / n,
        "mrr": sum(r["rr"] for r in rows) / n,
    }


def summarize_answers(items: list[dict], answers: dict) -> dict:
    done = [i for i in items if i["id"] in answers]
    answerable = [i for i in done if i["category"] != "unanswerable"]
    unanswerable = [i for i in done if i["category"] == "unanswerable"]
    refused = [i for i in done if is_refusal(answers[i["id"]]["answer"])]
    correct_refusals = [i for i in refused if i["category"] == "unanswerable"]
    by_category: dict[str, list[bool]] = {}
    for i in done:
        by_category.setdefault(i["category"], []).append(answer_correct(i, answers[i["id"]]["answer"]))
    buckets = []
    for lo, hi in CONFIDENCE_BUCKETS:
        inside = [i for i in answerable if lo <= answers[i["id"]]["confidence_score"] < hi]
        buckets.append({
            "range": f"{lo:.2f}-{min(hi, 1.0):.2f}",
            "n": len(inside),
            "accuracy": (sum(answer_correct(i, answers[i["id"]]["answer"]) for i in inside) / len(inside)) if inside else None,
        })
    return {
        "n": len(done),
        "answer_accuracy": sum(answer_correct(i, answers[i["id"]]["answer"]) for i in answerable) / max(len(answerable), 1),
        "n_answerable": len(answerable),
        "refusal_recall": len(correct_refusals) / max(len(unanswerable), 1),
        "refusal_precision": len(correct_refusals) / max(len(refused), 1),
        "false_refusals": len(refused) - len(correct_refusals),
        "n_unanswerable": len(unanswerable),
        "by_category": {k: (sum(v) / len(v), len(v)) for k, v in sorted(by_category.items())},
        "calibration": buckets,
        "median_seconds": sorted(answers[i["id"]]["seconds"] for i in done)[len(done) // 2] if done else None,
    }


def pct(x) -> str:
    return "–" if x is None else f"{100 * x:.0f}%"


def build_report() -> None:
    _, items = load_eval_set()
    md = ["# SAGE evaluation report", "", f"Eval set: {len(items)} questions over 6 sources "
          f"({sum(1 for i in items if i['category'] == 'unanswerable')} unanswerable).", ""]
    tex = ["% Generated by backend/eval/run_eval.py --report"]

    retrieval_files = sorted(RESULTS_DIR.glob("retrieval_*.json"))
    baseline = RESULTS_DIR / f"retrieval_{model_slug(DEFAULT_MODEL)}.json"
    if baseline.exists():
        data = load_json(baseline, {})
        md += [f"## Retrieval ablation ({data['model']})", "",
               "| Configuration | Context recall | Recall@k | MRR |", "|---|---|---|---|"]
        tex += [r"\begin{table}[t]\centering\caption{Retrieval ablation (" + data["model"].replace("_", r"\_") + r").}\label{tab:ablation}",
                r"\begin{tabular}{lccc}\hline Configuration & Ctx.\ recall & Recall@$k$ & MRR \\ \hline"]
        for name, cfg in data["configs"].items():
            s = summarize_retrieval(cfg["rows"])
            md.append(f"| {name} | {pct(s['context_recall'])} | {pct(s['recall_at_k'])} | {s['mrr']:.2f} |")
            tex.append(f"{name.replace('+', '+~')} & {pct(s['context_recall'])} & {pct(s['recall_at_k'])} & {s['mrr']:.2f} \\\\")
        tex += [r"\hline\end{tabular}\end{table}", ""]
        md.append(f"\n{summarize_retrieval(next(iter(data['configs'].values()))['rows'])['n']} retrieval-scored questions.\n")

    if len(retrieval_files) > 1:
        md += ["## Embedding models (full pipeline)", "", "| Model | Context recall | Recall@k | MRR | ms/query |", "|---|---|---|---|---|"]
        tex += [r"\begin{table}[t]\centering\caption{Embedding model comparison (full pipeline).}\label{tab:embeddings}",
                r"\begin{tabular}{lccc}\hline Model & Ctx.\ recall & Recall@$k$ & MRR \\ \hline"]
        for path in retrieval_files:
            data = load_json(path, {})
            cfg = data["configs"]["Full (+ overview/position)"]
            s = summarize_retrieval(cfg["rows"])
            md.append(f"| {data['model']} | {pct(s['context_recall'])} | {pct(s['recall_at_k'])} | {s['mrr']:.2f} | {cfg['ms_per_query']:.0f} |")
            tex.append(f"\\texttt{{{data['model']}}} & {pct(s['context_recall'])} & {pct(s['recall_at_k'])} & {s['mrr']:.2f} \\\\")
        tex += [r"\hline\end{tabular}\end{table}", ""]

    for path in sorted(RESULTS_DIR.glob("answers_*.json")):
        s = summarize_answers(items, load_json(path, {}))
        label = path.stem.removeprefix("answers_")
        md += [f"## Answers — full system ({label})", "",
               f"- Answer accuracy (answerable): **{pct(s['answer_accuracy'])}** of {s['n_answerable']}",
               f"- Refusal recall (unanswerable refused): **{pct(s['refusal_recall'])}** of {s['n_unanswerable']}",
               f"- Refusal precision: **{pct(s['refusal_precision'])}** ({s['false_refusals']} false refusals)",
               f"- Median answer latency: {s['median_seconds']}s", "",
               "| Category | Accuracy | n |", "|---|---|---|"]
        md += [f"| {k} | {pct(acc)} | {n} |" for k, (acc, n) in s["by_category"].items()]
        md += ["", "### Confidence calibration (answerable questions)", "", "| Confidence | n | Accuracy |", "|---|---|---|"]
        md += [f"| {b['range']} | {b['n']} | {pct(b['accuracy'])} |" for b in s["calibration"]]
        md.append("")
        tex += [r"\begin{table}[t]\centering\caption{Answer quality and refusals (full system).}\label{tab:answers}",
                r"\begin{tabular}{lc}\hline Metric & Value \\ \hline",
                f"Answer accuracy ({s['n_answerable']} answerable) & {pct(s['answer_accuracy'])} \\\\",
                f"Refusal recall ({s['n_unanswerable']} unanswerable) & {pct(s['refusal_recall'])} \\\\",
                f"Refusal precision & {pct(s['refusal_precision'])} \\\\",
                r"\hline\end{tabular}\end{table}", "",
                r"\begin{table}[t]\centering\caption{Confidence calibration on answerable questions.}\label{tab:calibration}",
                r"\begin{tabular}{lcc}\hline Confidence & $n$ & Accuracy \\ \hline"]
        tex += [f"{b['range']} & {b['n']} & {pct(b['accuracy'])} \\\\" for b in s["calibration"]]
        tex += [r"\hline\end{tabular}\end{table}", ""]

    tex = [line if line.startswith("%") else line.replace("%", r"\%") for line in tex]
    (RESULTS_DIR / "report.md").write_text("\n".join(md) + "\n")
    (RESULTS_DIR / "tables.tex").write_text("\n".join(tex) + "\n")
    print("\n".join(md))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--retrieval", action="store_true")
    parser.add_argument("--answers", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--model", default=None, help="embedding model (uses collection sage_chunks_<slug>)")
    parser.add_argument("--pace", type=float, default=8.0, help="seconds between answer calls (free tiers)")
    parser.add_argument("--fresh", action="store_true", help="ignore cached answers")
    args = parser.parse_args()

    model = args.model or os.environ.get("EMBEDDING_MODEL_NAME") or DEFAULT_MODEL
    if args.model and args.model != DEFAULT_MODEL:
        # Must be set before app settings are first read.
        os.environ["EMBEDDING_MODEL_NAME"] = args.model
        os.environ["CHROMA_COLLECTION_NAME"] = f"sage_chunks_{model_slug(args.model)}"
    sys.path.insert(0, str(EVAL_DIR.parent))

    if args.retrieval:
        run_retrieval(model)
    if args.answers:
        run_answers(model, args.pace, args.fresh)
    if args.report or args.retrieval or args.answers:
        build_report()
    if not (args.retrieval or args.answers or args.report):
        parser.print_help()


if __name__ == "__main__":
    main()

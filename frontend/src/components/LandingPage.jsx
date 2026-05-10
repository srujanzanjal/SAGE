import { ArrowRight, BrainCircuit, FileText, GitBranch, Globe, Video } from "lucide-react";

const modules = [
  {
    key: "website",
    title: "Website",
    icon: Globe,
    accent: "from-cyan-500/15 to-blue-500/15 border-cyan-200/70",
    description: "Crawl and analyze websites with grounded citations and crawl progress.",
    tag: "Playwright crawl",
  },
  {
    key: "pdf",
    title: "PDF / Document",
    icon: FileText,
    accent: "from-violet-500/15 to-fuchsia-500/15 border-violet-200/70",
    description: "Upload PDFs and ask questions over page-grounded chunks and snippets.",
    tag: "Page citations",
  },
  {
    key: "video",
    title: "Video",
    icon: Video,
    accent: "from-emerald-500/15 to-teal-500/15 border-emerald-200/70",
    description: "Ingest YouTube transcripts and answer with timestamped citations.",
    tag: "Transcript mode",
  },
  {
    key: "github",
    title: "GitHub Repo",
    icon: GitBranch,
    accent: "from-slate-700/15 to-slate-900/15 border-slate-300/70",
    description: "Analyze public repositories with file-path and line-range citations.",
    tag: "File-line citations",
  },
];

export default function LandingPage({ onSelectType }) {
  return (
    <main className="min-h-screen px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-7xl items-center">
        <div className="w-full space-y-8">
          <section className="overflow-hidden rounded-[2rem] border border-slate-200/70 bg-white/75 p-6 shadow-[0_24px_80px_-48px_rgba(15,23,42,0.35)] backdrop-blur sm:p-8 lg:p-10">
            <div className="grid gap-8 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)] lg:items-center">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-indigo-700">
                  <BrainCircuit size={14} /> SAGE source-grounded AI
                </div>
                <h1 className="mt-5 text-4xl font-black tracking-tight text-slate-950 sm:text-5xl lg:text-6xl">
                  Ask grounded questions over websites, documents, videos, and GitHub repos.
                </h1>
                <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg">
                  SAGE ingests public knowledge sources, stores citations, and answers with confidence scores, snippets, and source-aware reasoning.
                </p>

                <div className="mt-6 flex flex-wrap gap-3 text-sm">
                  {[
                    "Grounded answers",
                    "Confidence scores",
                    "Timestamp citations",
                    "File-line links",
                  ].map((item) => (
                    <span key={item} className="rounded-full border border-slate-200 bg-white px-3 py-2 font-medium text-slate-700 shadow-sm">
                      {item}
                    </span>
                  ))}
                </div>
              </div>

              <div className="rounded-[1.75rem] border border-slate-200 bg-slate-950 p-6 text-white shadow-2xl shadow-slate-950/20">
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-indigo-200">What SAGE can do</p>
                <div className="mt-4 space-y-4 text-sm text-slate-300">
                  <div className="rounded-2xl bg-white/5 p-4">
                    <p className="font-semibold text-white">1. Ingest a source</p>
                    <p className="mt-1">Website, PDF, video transcript, or GitHub repository.</p>
                  </div>
                  <div className="rounded-2xl bg-white/5 p-4">
                    <p className="font-semibold text-white">2. Index the content</p>
                    <p className="mt-1">Chunks are embedded, stored, and retrieved with metadata.</p>
                  </div>
                  <div className="rounded-2xl bg-white/5 p-4">
                    <p className="font-semibold text-white">3. Ask grounded questions</p>
                    <p className="mt-1">Answers include citations, snippets, and relevance scoring.</p>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
            {modules.map((module) => {
              const Icon = module.icon;
              return (
                <button
                  key={module.key}
                  onClick={() => onSelectType(module.key)}
                  className={`group text-left rounded-[1.75rem] border bg-gradient-to-br p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-xl ${module.accent}`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="rounded-2xl bg-slate-950/90 p-3 text-white shadow-lg shadow-slate-950/15">
                      <Icon size={24} />
                    </div>
                    <ArrowRight size={20} className="mt-1 text-slate-500 transition group-hover:translate-x-1 group-hover:text-slate-950" />
                  </div>
                  <h2 className="mt-5 text-2xl font-bold text-slate-950">{module.title}</h2>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{module.description}</p>
                  <div className="mt-4 inline-flex rounded-full bg-white/80 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-600 shadow-sm">
                    {module.tag}
                  </div>
                </button>
              );
            })}
          </section>
        </div>
      </div>
    </main>
  );
}

export default function ModeSelector({ mode, onChange }) {
  return (
    <div className="inline-flex rounded-2xl bg-slate-100 p-1 text-sm">
      <button
        onClick={() => onChange("grounded")}
        className={`rounded-xl px-4 py-2 font-semibold ${mode === "grounded" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}
      >
        Grounded
      </button>
      <button
        onClick={() => onChange("exploratory")}
        className={`rounded-xl px-4 py-2 font-semibold ${mode === "exploratory" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}
      >
        Exploratory
      </button>
    </div>
  );
}

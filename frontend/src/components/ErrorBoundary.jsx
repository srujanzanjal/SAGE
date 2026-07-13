import { Component } from "react";
import { AlertTriangle } from "lucide-react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("SAGE crashed:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="mx-auto mt-16 max-w-lg rounded-3xl border border-rose-200 bg-white p-6 text-center shadow-sm">
          <AlertTriangle className="mx-auto mb-3 text-rose-500" size={28} />
          <h2 className="text-lg font-bold text-slate-950">Something went wrong</h2>
          <p className="mt-2 text-sm text-slate-600">
            This part of SAGE hit an unexpected error. You can reload to keep going.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700"
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles.css";

/** Last-resort render guard: a component crash shows a recovery card
 * instead of a blank page, and one click reloads the app. */
class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-background p-6 text-foreground">
          <div className="max-w-md rounded-lg border border-border bg-card p-6 text-center">
            <h1 className="text-lg font-semibold">Something went wrong</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              The dashboard hit an unexpected error. Your library is safe on disk —
              reloading usually fixes it.
            </p>
            <pre className="mt-3 max-h-32 overflow-auto rounded-md bg-muted p-2 text-left text-xs text-muted-foreground">
              {this.state.error.message}
            </pre>
            <button
              className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground"
              onClick={() => window.location.reload()}
            >
              Reload SessionIQ
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);

import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps { children: ReactNode }
interface ErrorBoundaryState { hasError: boolean }

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState { return { hasError: true }; }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // Keep internal exception details out of the public dashboard.
  }

  render() {
    if (this.state.hasError) {
      return <main className="app-shell" role="alert"><section className="error-panel"><div><h1>Dashboard couldn’t render</h1><p>Reload the page to try again. If the problem continues, contact the service operator.</p></div><button type="button" className="btn btn-secondary" onClick={() => window.location.reload()}>Reload dashboard</button></section></main>;
    }
    return this.props.children;
  }
}
